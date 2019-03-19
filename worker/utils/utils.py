import os
import sys
import json
import time
import asyncio
import asyncpg
import logging
import requests
from lxml import html
from redis import StrictRedis
from datetime import datetime
from selenium.webdriver import Firefox, FirefoxProfile
from selenium.webdriver.firefox.options import Options


logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='worker.log',
                    datefmt='%d-%b-%y %H:%M:%S')

API_HOST = os.environ.get('API_HOST')
API_PORT = os.environ.get('API_PORT')
REDIS_HOST = os.environ.get('REDIS_HOST')
REDIS_PORT = os.environ.get('REDIS_PORT')
POSTGRES_HOST = os.environ.get('POSTGRES_HOST')
POSTGRES_PORT = os.environ.get('POSTGRES_PORT')
POSTGRES_USER = os.environ.get('POSTGRES_USER')
POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD')
POSTGRES_DB = os.environ.get('POSTGRES_DB')

postgres_details = {
    'host': POSTGRES_HOST,
    'user': POSTGRES_USER,
    'password': POSTGRES_PASSWORD,
    'database': POSTGRES_DB,
    'port': POSTGRES_PORT
}


async def get_failed_data():
    try:
        cache = StrictRedis(host=REDIS_HOST, port=REDIS_PORT)

        conn = await asyncpg.connect(**postgres_details)
        failed_items = await conn.fetch(
            '''SELECT * FROM parts_data
               WHERE part_num_analyzed = 'failed'
               LIMIT 300;'''
        )

        for failed in failed_items:  # fix this
            cache.rpush('failed', failed)

    except Exception as error:
        logging.error(f'{error}', exc_info=True)
        print(f'ERROR: {error}. Check master.log for tracestack.')

    finally:
        if conn:
            await conn.close()


async def store_data(data_list):
    sql_insert = '''INSERT INTO parts_data (
                        url_list_id,
                        url,
                        part_num,
                        part_num_analyzed,
                        details,
                        specs,
                        datasheet_url,
                        issued_time,
                        issued_to,
                        completed_time
                    ) VALUES ($1, $2, $3, $4, $5::jsonb,
                        $6::jsonb, $7, $8, $9, $10)'''

    sql_update = '''UPDATE parts_data
                    SET part_num_analyzed=$1,
                        details=$2::jsonb,
                        specs=$3::jsonb,
                        datasheet_url=$4,
                        issued_time=$5,
                        issued_to=$6,
                        completed_time=$7
                    WHERE url = $1;'''

    try:
        async with asyncpg.create_pool(**postgres_details) as pool:
            for data in data_list:
                async with pool.acquire() as conn:
                    # Functions for making a custom JSONB codec
                    # to autmatically serialize and de-serialize
                    # into JSONB as you pull and push into the db.
                    def _encoder(value):
                        return b'\x01' + json.dumps(value).encode('utf-8')

                    def _decoder(value):
                        return json.loads(value[1:].decode('utf-8'))

                    await conn.set_type_codec(
                        'jsonb',
                        encoder=_encoder,
                        decoder=_decoder,
                        schema='pg_catalog',
                        format='binary'
                    )

                    completed_time = data.get('completed_time')
                    time_complete = datetime.now() if completed_time else None

                    row = await conn.fetchrow(
                        'SELECT * FROM parts_data WHERE url = $1',
                        data.get('url')
                    )

                    if row:
                        await conn.execute(
                            sql_update,
                            data.get('part_num_analyzed'),
                            data.get('details'),
                            data.get('specs'),
                            data.get('datasheet_url'),
                            datetime.now(),
                            data.get('issued_to'),
                            time_complete,
                        )

                    else:
                        await conn.execute(
                            sql_insert,
                            data.get('url_list_id'),
                            data.get('url'),
                            data.get('part_num'),
                            data.get('part_num_analyzed'),
                            data.get('details'),
                            data.get('specs'),
                            data.get('datasheet_url'),
                            datetime.now(),
                            data.get('issued_to'),
                            time_complete,
                        )

        _clear_cache()
        print('Successfully stored data in postgres...')
        logging.info('Successfully stored data in postgres...')

    except Exception as error:
        logging.error(f'{error}', exc_info=True)
        print(f'ERROR: {error}. Check master.log for tracestack.')


def scrape_data(urls_data, timeout, ip):
    print('Scraping...')

    try:
        cache = StrictRedis(host=REDIS_HOST, port=REDIS_PORT)

        opts = Options()
        opts.headless = True
        browser = Firefox(options=opts)

        for url_info in urls_data:
            url = url_info.get('part_url')
            url_list_id = url_info.get('ID')
            part_number = url_info.get('part_name')
            time_now = time.time()
            data = {
                'url_list_id': url_list_id,
                'url': url,
                'part_num': part_number,
                'part_num_analyzed': 'failed',
                'details': None,
                'specs': None,
                'datasheet_url': None,
                'issued_time': time_now,
                'issued_to': ip,
                'completed_time': None
            }

            try:
                browser.get(url)
                source = browser.page_source
                tree = html.fromstring(source.encode())

                partpage = tree.xpath('//span[@class="part-number"]')
                if not partpage:
                    raise Exception('Landed not on the part page')

                hrefs = tree.xpath('//@href')
                for item in hrefs:
                    if item.startswith('/pdf'):
                        data['datasheet_url'] = item

                spec_keys = tree.xpath(
                    '//table[@class="specs"]//td[1]//text()')
                spec_values = tree.xpath(
                    '//table[@class="specs"]//td[2]//text()')

                detail_keys = tree.xpath('//div/b/text()')
                detail_values = tree.xpath(
                    '//*[@id="part-details"]//div/text()')

                details = _make_details(detail_keys, detail_values)
                specs = _make_specs(spec_keys, spec_values)

                data['details'] = details
                data['sepcs'] = specs
                data['part_num_analyzed'] = 'success'
                data['completed_time'] = time_now

                # Cache the data in redis
                cache.rpush('pages', json.dumps(data))
                time.sleep(timeout)

            except Exception as error:
                logging.error(f'{error}.', exc_info=True)
                print(f'ERROR: {error}. Check master.log for tracestack.')

                # Cache the failed data in redis
                cache.rpush('pages', json.dumps(data))
                time.sleep(timeout)

        # Returns the data from the Redis Cache
        # and deserializes it back to normal structure.
        scraped_data = cache.lrange('pages', 0, -1)
        scraped_data = _deserialize(scraped_data)

        return scraped_data

    except Exception:
        raise

    finally:
        if browser:
            browser.quit()
        # For assurance that there are no
        # mem leaks from the browser
        os.system('killall firefox-esr')


def get_ip():
    try:
        ip = requests.get('https://api.ipify.org').text

    except:
        try:
            ip = requests.get('https://ident.me/').text

        except Exception as error:
            logging.error(f'{error}. Cannot get ip', exc_info=True)
            print(f'ERROR: {error}. Check master.log for tracestack.')
            sys.exit(1)

    return ip


def get_url_list():
    urls = requests.get(f'http://{API_HOST}:{API_PORT}/api/urls')

    url_list = urls.json()
    last_item = url_list[len(url_list) - 1]

    return url_list, last_item


def _make_details(detail_keys, detail_values):
    details = {}
    for detail_key in detail_keys:
        details[detail_key[:-1]] = ''

    clean_values = _clean(detail_values)

    for index, clean_value in enumerate(clean_values):
        details[detail_keys[index][:-1]] = clean_value

    return details


def _make_specs(spec_keys, spec_values):
    specs = {}
    clean_keys = _clean(spec_keys)
    clean_values = _clean(spec_values)

    for index, clean_value in enumerate(clean_values):
        specs[clean_keys[index]] = clean_value

    return specs


def _clean(values):
    clean_items = []
    for value in values:
        value = value.replace('\n', '')
        value = value.replace('\t', '')

        if value and not value.lower().startswith('show'):
            clean_items.append(value.strip())

    return clean_items


def _deserialize(data):
    deserialized_data = []
    for item in data:
        deserialized_data.append(json.loads(item))

    return deserialized_data


def _clear_cache():
    try:
        cache = StrictRedis(host=REDIS_HOST, port=REDIS_PORT)
        cache.flushall()

    except Exception as error:
            logging.error(f'{error}. Cannot get ip', exc_info=True)
            print(f'ERROR: {error}. Check master.log for tracestack.')

