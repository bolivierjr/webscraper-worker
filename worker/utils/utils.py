import os
import sys
import json
import time
import logging
import requests
from lxml import html
from redis import StrictRedis
from datetime import datetime
from selenium.webdriver import Firefox, FirefoxProfile
from selenium.webdriver.firefox.options import Options


API_HOST = os.environ.get('API_HOST')
API_PORT = os.environ.get('API_PORT')
REDIS_HOST = os.environ.get('REDIS_HOST')
REDIS_PORT = os.environ.get('REDIS_PORT')


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
            timestamp = str(datetime.now())
            data = {
                'url_list_id': url_list_id,
                'url': url,
                'part_num': part_number,
                'part_num_analyzed': 'failed',
                'details': None,
                'specs': None,
                'datasheet_url': None,
                'issued_time': timestamp,
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
                data['completed_time'] = timestamp

                # Cache the data in redis
                cache.rpush('pages', json.dumps(data))
                time.sleep(timeout)

            except Exception as error:
                logging.error(f'{error}.', exc_info=True)
                print(f'ERROR: {error}. Check master.log for tracestack.')

                # Cache the failed data in redis
                cache.rpush('pages', json.dumps(data))
                time.sleep(timeout)

    except Exception:
        raise

    finally:
        if browser:
            browser.quit()
        # For assurance that there are no
        # mem leaks from the browser
        os.system('killall firefox-esr')


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
    print(specs)
    return specs


def _clean(values):
    clean_items = []
    for value in values:
        value = value.replace('\n', '')
        value = value.replace('\t', '')

        if value and not value.lower().startswith('show'):
            clean_items.append(value.strip())

    return clean_items
