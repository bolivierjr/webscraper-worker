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


def main():
    print('Worker running...')

    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',
                        filename='worker.log',
                        datefmt='%d-%b-%y %H:%M:%S')

    ip = utils.get_ip()

    while True:
        try:
            url_list, last_item = utils.get_url_list()

            # last_item = {'done': True}  # for testing
            if 'timeout' in last_item.keys():
                timeout = last_item.get('timeout')
                url_list.remove(last_item)

                cache_data = utils.scrape_data(url_list, timeout, ip)
                store_data = utils.store_data(cache_data)
                asyncio.run(store_data)

            elif 'error' in last_item.keys():
                time.sleep(30)
                continue

            elif 'done' in last_item.keys():
                failed = utils.get_failed_data()
                asyncio.run(failed)  # fix this
                time.sleep(100)

        except (requests.exceptions.RequestException, Exception) as error:
            logging.error(f'{error}', exc_info=True)
            print(f'ERROR: {error}. Check master.log for tracestack.')


if __name__ == '__main__':
    main()
