# -*- coding: utf-8 -*-
"""
Created on 2018/10/31

@author: gaoan
"""
import os

from tigeropen.common.consts import Language
from tigeropen.tiger_open_config import TigerOpenClientConfig
from tigeropen.common.util.signature_utils import read_private_key


def get_client_config():
    """
    https://www.itiger.com/openapi/info 开发者信息获取
    :return:
    """
    config_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'config', 'tiger_openapi_config.properties'))
    private_key_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'config', 'private_key.pem'))
    client_config = TigerOpenClientConfig(
        sandbox_debug=False,  # 生产环境
        props_path=config_path
    )
    client_config.private_key = read_private_key(private_key_path)
    client_config.language = Language.zh_CN
    client_config.timeout = 60
    # client_config.timezone = 'US/Eastern' # 设置全局时区
    return client_config

if __name__ == '__main__':
    print(get_client_config().props_path)
