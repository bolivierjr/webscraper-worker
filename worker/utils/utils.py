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

        proxy_host = '45.115.175.20'
        proxy_port = 32158

        profile = FirefoxProfile()
        profile.set_preference("network.proxy.type", 1)
        profile.set_preference('network.proxy.http', proxy_host)
        profile.set_preference('network.proxy.http_port', proxy_port)
        profile.set_preference('network.proxy.ssl', proxy_host)
        profile.set_preference('network.proxy.ssl_port', proxy_port)

        browser = Firefox(firefox_profile=profile, options=opts)

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
                hrefs = tree.xpath('//@href')
                specs = tree.xpath('//td/text()')

                print(specs)
                if not partpage:
                    raise Exception('Landed not on the part page')

                for item in hrefs:
                    if item.startswith('/pdf'):
                        data['datasheet_url'] = item

                time.sleep(1000)

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
