#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
简单测试BrokerTigerAPI的初始化方法
直接使用真实接口进行测试
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

if __name__ == "__main__":
    from src.api.broker_tiger_api import BrokerTigerAPI

    api = BrokerTigerAPI()
    account_profile = api.get_account_profile('PAPER')
    print(f"  账户: {account_profile}")
    assets = api.get_assets(account_profile)

    contracts = api.get_contacts('AAPL')

    order = api.create_order(account_profile.account, contracts)


