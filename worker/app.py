#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import sys
import time
import requests
import logging
from utils import utils


def main():
    print('Worker running...')

    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',
                        filename='worker.log',
                        datefmt='%d-%b-%y %H:%M:%S')

    ip = utils.get_ip()

    while True:
        try:
            url_list, last_item = utils.get_url_list()

            if 'timeout' in last_item.keys():
                timeout = last_item.get('timeout')
                url_list.remove(last_item)

                utils.scrape_data(url_list, timeout, ip)

            elif 'error' in last_item.keys():
                time.sleep(30)
                continue

            elif 'done' in last_item.keys():
                print('you are done')

        except (requests.exceptions.RequestException, Exception) as error:
            logging.error(f'{error}', exc_info=True)
            print(f'ERROR: {error}. Check master.log for tracestack.')

        time.sleep(5)

if __name__ == '__main__':
    main()
