#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import asyncio
import logging
import requests
from utils import utils
from redis import StrictRedis


logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='worker.log',
                    datefmt='%d-%b-%y %H:%M:%S')

REDIS_HOST = os.environ.get('REDIS_HOST')
REDIS_PORT = os.environ.get('REDIS_PORT')

timeout = 3  # Default timeout


def main():
    print('Worker running...')

    while True:
        try:
            cached = StrictRedis(host=REDIS_HOST, port=REDIS_PORT)

            ip = utils.get_ip()
            url_list, last_item = utils.get_url_list()

            if 'timeout' in last_item.keys():
                # Set timeout by env variable
                global timeout
                timeout = last_item.get('timeout')
                url_list.remove(last_item)

                cache_data = utils.scrape_data(url_list, timeout, ip)
                store_data = utils.store_data(cache_data)
                asyncio.run(store_data)

            elif 'error' in last_item.keys():
                logging.error('Sleeping for 30 secs to retry again...')
                time.sleep(30)
                continue

            elif 'done' in last_item.keys():
                failed_urls = utils.get_failed_data(timeout, ip)
                asyncio.run(failed_urls)

                failed_url_list = cached.lrange('failed_urls', 0, -1)
                deserialized_list = utils._deserialize(failed_url_list)

                cache_data = utils.scrape_data(deserialized_list, timeout, ip)
                store_data = utils.store_data(cache_data)
                asyncio.run(store_data)

        except (requests.exceptions.RequestException, Exception) as error:
            logging.error(f'{error}', exc_info=True)
            print(f'ERROR: {error}. Check master.log for tracestack.')
            time.sleep(1)


if __name__ == '__main__':
    main()
