#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import time
import redis
import requests
import logging


def get_url_list():
    api_host = os.environ.get('API_HOST')
    api_port = os.environ.get('API_PORT')
    urls = requests.get(f'http://{api_host}:{api_port}/api/urls')

    return urls.json()

if __name__ == '__main__':
    print('Worker running...')

    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',
                        filename='worker.log',
                        datefmt='%d-%b-%y %H:%M:%S')

    while True:
        try:
            timeout = None
            url_list = get_url_list()
            last_item = url_list[len(url_list) - 1]

            if 'timeout' in last_item.keys():
                timeout = last_item.get('timeout')
                url_list.remove(last_item)

            elif 'error' in last_item.keys():
                time.sleep(30)
                continue

            elif 'done' in last_item.keys():
                pass

            for url_info in url_list:
                pass

        except (requests.exceptions.RequestException, Exception) as error:
            logging.error(f'{error}', exc_info=True)
            print(f'ERROR: {error}. Check master.log for tracestack.')

        time.sleep(5)
