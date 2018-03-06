# -*- coding: utf8 -*-

configs = {
    'set': {                   #乘车信息
        'station_dates': ['2018-03-14'],
        'station_trains': ['G6482'],
        'from_station': '广州',
        'to_station': '邵东',
        'set_type': ['二等座'],       # seat
        'is_more_ticket': True,
        'ticke_peoples': ['曾尔比'],
    },
    'account': {                #账号
        'username': '276957690@qq.com',
        'pwd': 'secret26'
    },
    'is_auto_code': False,      # 自动识别二维码
    'is_cdn': True,             # 使用cdn
    'to_email': '276957690@qq.com',             # 订票成功收件邮箱
    'email_conf': {  # 账号
        'to_email': 'qq.com',
        'username': '123456',
        'password': '123456',
        'host': 'smtp.qq.com',
        'port': '25',
    },
}
