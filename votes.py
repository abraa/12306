#!/usr/bin/env python3
# encoding= 'utf8'
import datetime
import random
import json
import re
import ssl
import time
from urllib import parse

from config import logger
from config import configCommon
from config.ticketConf import configs
from config.urlConf import urls
from exception.PassengerUserException import PassengerUserException
from util.httpClient import httpClient
from util import my_util, cdnUtil
from exception.UserPasswordException import UserPasswordException
from concurrent import futures


class Votes(object):

    httpClient = None
    confUrl = None
    _cdn = None
    _host = None

    def __init__(self):
        self.confUrl = urls                     # http请求参数
        self.httpClient = httpClient()          # http请求客户端
        self.is_check_user = dict()             # 用户登录状态
        self.configs = configs                  # 购票配置参数
        self.ticket_black_list = dict()         # 车次黑名单
        self.ticket_black_list_time = 2         # 黑名单失效时间 (分钟)
        self.station = my_util.read_station()   # 车站名称对应简写
        self.seat = my_util.read_seat()         # 车站座位对应简写和位置
        self.user_info = None                   # 乘车人信息
        pass

    @property
    def cdn(self):
        return self._cdn

    @cdn.setter
    def cdn(self, cdn):
        self._cdn = cdn

    @property
    def host(self):
        if self.cdn:
            return 'https://'+self.cdn
        else:
            return 'https://kyfw.12306.cn'

    # 登录
    def login(self):
        user, passwd = self.configs['account']["username"], self.configs['account']["pwd"]
        if not user or not passwd:
            raise UserPasswordException("温馨提示: 用户名或者密码为空，请仔细检查")
        login_num = 0
        while True:
            # 重复调用3次
            if 3 <= login_num:
                break
            # 先获取cookie
            self._send(self.confUrl['loginInit'])
            # 再获取验证图片
            self.confUrl["getCodeImg"]["req_url"] = self.confUrl["getCodeImg"]["req_url"].format(random.random())
            result = self._send(self.confUrl['getCodeImg'])
            # 保存验证码图片到本地
            img_path = './tkcode'
            try:
                print("下载验证码成功")
                open(img_path, 'wb').write(result)
            except OSError as e:
                print(e)
            # 识别验证码图片
            rand_code = my_util.get_rand_code(self.configs['is_auto_code'], file_path=img_path)
            # auth
            self._send(self.confUrl['auth'], data={'appid': "otn"})
            # 调用登录接口登录
            login_num += 1
            if self.verify_code(rand_code):
                data = {
                    "username": user,
                    "password": passwd,
                    "appid": "otn"
                }
                tresult = self._send(self.confUrl['login'], data=data)
                # 结果处理 uamtk
                if 'result_code' in tresult and tresult["result_code"] == 0:
                    print("登录成功")
                    tk = self._send(self.confUrl['auth'], data={'appid': "otn"})
                    if "newapptk" in tk and tk["newapptk"]:
                        uamtk = tk["newapptk"]
                    else:
                        continue
                elif 'result_message' in tresult and tresult['result_message']:
                    messages = tresult['result_message']
                    if messages.find("密码输入错误") is not -1:
                        raise UserPasswordException("{0}".format(messages))
                    else:
                        print("登录失败: {0}".format(messages))
                        print("尝试重新登陆")
                        continue
                else:
                    continue
                if uamtk:               # 校验码
                    self.uamauthclient(uamtk)
                    break
        return True


    # 检查余票
    def check_ticket(self, host):
        res = {'host': host, 'result': []}
        for station_date in configs['set']['station_dates']:
            # 1,查询当前日期所有车次
            select_url = self.confUrl['select_url']
            select_url["req_url"] = select_url["req_url"].format(
                station_date, self.station[self.configs['set']['from_station']], self.station[self.configs['set']['to_station']])
            result = self._send(urlconf=select_url)
            value = result['data']
            if not value:
                print(u'{0}-{1} 车次坐席查询为空...'.format(self.configs['set']['from_station'], self.configs['set']['to_station']))
            else:
                if value['result']:
                    # 2.排除不在选择内的此次
                    for i in value['result']:
                        ticket_info = i.split('|')
                        if ticket_info[11] == "Y" and ticket_info[1] == "预订":  # 可以进行预订票
                            result = []
                            for j in self.configs["set"]["set_type"]:
                                is_ticket_pass = ticket_info[self.seat[j]['seat']]    # 座位 [二等座]
                                if is_ticket_pass != '' and is_ticket_pass != '无' and ticket_info[
                                    3] in configs['set']['station_trains'] and is_ticket_pass != '*':  # 过滤有效目标车次 station_trains
                                    train_no = ticket_info[3]                        # 车次
                                    print(u'车次: ' + train_no + ' 始发车站: ' + self.configs['set']['from_station'] + ' 终点站: ' +
                                          self.configs['set']['to_station'] + ':' + ticket_info[self.seat[j]['seat']])
                                    if train_no in self.ticket_black_list and (                      # 检查黑名单是否过期
                                            datetime.datetime.now() - self.ticket_black_list[
                                        train_no]).seconds / 60 < int(self.ticket_black_list_time):
                                        print(u"该车次{} 正在被关小黑屋，跳过此车次".format(train_no))
                                        break
                                    result.append({'secretStr': ticket_info[0], 'train_no': train_no, 'seat': j,
                                                   'from_station': self.configs['set']['from_station'],
                                                   'to_station': self.configs['set']['to_station'],
                                                   'station_date': station_date})                   # 加密字符串
                                else:
                                    pass
                            if result:
                                res['result'].append(result)
                        else:
                            pass
                else:
                    print("车次配置信息有误，或者返回数据异常，请检查 {}".format(value))
        return res

    # 购买车票 - 下单
    def buy_ticket(self, param):
        for result in param['result']:
            for result2 in result:
                data = {
                    'secretStr': parse.unquote(result2['secretStr']),
                    'train_date': result2['station_date'],
                    'back_train_date': result2['station_date'],
                    'tour_flag': 'dc',
                    'purpose_codes': 'ADULT',
                    'query_from_station_name': result2['from_station'],
                    'query_to_station_name': result2['to_station'],
                    'undefined': ''
                }
                print("正在预定{0}  乘车日期: {1}  车次{2} 查询有票  cdn轮询IP {4}  当前时间{3}ms".format('',
                                                                                            result2['station_date'],
                                                                                            result2['train_no'],
                                                                                            datetime.datetime.now(),
                                                                                            param['host'],
                                                                                            ))
                submitResult = self._send(self.confUrl["submit_station_url"], data)
                if 'data' in submitResult and submitResult['data']:
                    if submitResult['data'] == 'N':
                        print(u'出票成功')
                        return submitResult, result2
                    else:
                        print(u'出票失败')
                elif 'messages' in submitResult and submitResult['messages']:
                    print('ticketIsExitsException : ' + submitResult['messages'][0])

        return False

    # 获取乘客信息
    def getPassengerDTOs(self, token):
        """
        获取乘客信息
        :return:
        """
        get_passengerDTOs = self.confUrl["get_passengerDTOs"]
        get_data = {
            '_json_att': None,
            'REPEAT_SUBMIT_TOKEN': token
        }
        jsonData = self._send(get_passengerDTOs, get_data)
        if 'data' in jsonData and jsonData['data'] and 'normal_passengers' in jsonData['data'] and jsonData['data']['normal_passengers']:
            normal_passengers = jsonData['data']['normal_passengers']
            _normal_passenger = [normal_passengers[i] for i in range(len(normal_passengers)) if
                                 normal_passengers[i]["passenger_name"] in self.configs['set']['ticke_peoples']]
            print('_normal_passenger:')
            print(_normal_passenger)
            return _normal_passenger if _normal_passenger else [normal_passengers[0]]  # 如果配置乘车人没有在账号，则默认返回第一个用户
        else:
            if 'data' in jsonData and 'exMsg' in jsonData['data'] and jsonData['data']['exMsg']:
                print(jsonData['data']['exMsg'])
            elif 'messages' in jsonData and jsonData['messages']:
                print(jsonData['messages'][0])
            else:
                print(u"未查找到常用联系人")
                raise PassengerUserException(u"未查找到常用联系人,请先添加联系人在试试")

    # 提交订单前检查接口
    def checkOrderInfo(self, token, submit_station, user_info=None):
        """
        检查支付订单，需要提交REPEAT_SUBMIT_TOKEN
        passengerTicketStr : 座位编号,0,票类型,乘客名,证件类型,证件号,手机号码,保存常用联系人(Y或N)
        oldPassengersStr: 乘客名,证件类型,证件号,乘客类型
        :return:
        """
        if user_info is None:
            user_info = self.user_info
        passengerTicketStrList, oldPassengerStr = my_util.get_passenger_ticket_str(user_info, self.seat[submit_station['seat']]['type'])
        checkOrderInfoUrl = self.confUrl["checkOrderInfoUrl"]
        data = dict()
        data['cancel_flag'] = 2
        data['bed_level_order_num'] = "000000000000000000000000000000"
        # 乘客字符串前面加上座位标识
        data['passengerTicketStr'] = self.seat[submit_station['seat']]['type'] + "," + ",".join(passengerTicketStrList).rstrip("_{0}".format(self.seat[submit_station['seat']]['type']))
        data['oldPassengerStr'] = "".join(oldPassengerStr)
        data['tour_flag'] = 'dc'
        data['whatsSelect'] = 1
        data['REPEAT_SUBMIT_TOKEN'] = token
        # 提交
        checkOrderInfo = self._send(checkOrderInfoUrl, data)
        if 'data' in checkOrderInfo:
            if "ifShowPassCode" in checkOrderInfo["data"] and checkOrderInfo["data"]["ifShowPassCode"] == "Y":
                # 需要验证码
                return True, True
            if "ifShowPassCode" in checkOrderInfo["data"] and checkOrderInfo['data']['submitStatus'] is True:
                    print('车票提交通过，正在尝试排队')
                    return True, False
            else:
                # 出错
                print("checkOrderInfo : ")
                print(checkOrderInfo['data']["errMsg"])
        elif 'messages' in checkOrderInfo and checkOrderInfo['messages']:
            print(checkOrderInfo['messages'][0])
        return False

    # 排队查询
    def getQueueCount(self, token, ticketInfoForPassengerForm, submit_station):
        """
        # 模拟查询当前的列车排队人数的方法
        # 返回信息组成的提示字符串
        :param token:ticketInfoForPassengerForm:乘客信息, submit_station: 车次信息,is_need_code:是否需要验证码
        :return:
        """
        l_time = time.localtime(time.time())
        new_train_date = time.strftime("%a %b %d %Y", l_time)
        getQueueCountUrl = self.confUrl["getQueueCountUrl"]
        data = {
            'train_date': str(new_train_date) + " 00:00:00 GMT+0800 (中国标准时间)",
            'train_no': ticketInfoForPassengerForm['queryLeftTicketRequestDTO']['train_no'],
            'stationTrainCode': ticketInfoForPassengerForm['queryLeftTicketRequestDTO'][
                'station_train_code'],
            'seatType': self.seat[submit_station['seat']]['type'],
            'fromStationTelecode': ticketInfoForPassengerForm['queryLeftTicketRequestDTO']['from_station'],
            'toStationTelecode': ticketInfoForPassengerForm['queryLeftTicketRequestDTO']['to_station'],
            'leftTicket': ticketInfoForPassengerForm['leftTicketStr'],
            'purpose_codes': ticketInfoForPassengerForm['purpose_codes'],
            'train_location': ticketInfoForPassengerForm['train_location'],
            'REPEAT_SUBMIT_TOKEN': token,
        }
        getQueueCountResult = self._send(getQueueCountUrl, data)            # 查询
        if "status" in getQueueCountResult and getQueueCountResult["status"] is True:
            if "countT" in getQueueCountResult["data"]:
                ticket = getQueueCountResult["data"]["ticket"]
                ticket_split = sum(map(int, ticket.split(","))) if ticket.find(",") != -1 else ticket
                countT = getQueueCountResult["data"]["countT"]
                if int(countT) is 0:
                    if int(ticket_split) < len(self.user_info):
                        print(u"当前余票数小于乘车人数，放弃订票")
                    else:
                        print(u"排队成功, 当前余票还剩余: {0} 张".format(ticket_split))
                        return True
                else:
                    print(u"当前排队人数: {1} 当前余票还剩余:{0} 张，继续排队中".format(ticket_split, countT))
            else:
                print(u"排队发现未知错误{0}，将此列车 {1}加入小黑屋".format(getQueueCountResult, submit_station['train_no']))
                self.ticket_black_list[submit_station['train_no']] = datetime.datetime.now()
        elif "messages" in getQueueCountResult and getQueueCountResult["messages"]:
            print(u"排队异常，错误信息：{0}, 将此列车 {1}加入小黑屋".format(getQueueCountResult["messages"][0], submit_station['train_no']))
            self.ticket_black_list[submit_station['train_no']] = datetime.datetime.now()
        else:
            if "validateMessages" in getQueueCountResult and getQueueCountResult["validateMessages"]:
                print(str(getQueueCountResult["validateMessages"]))
                self.ticket_black_list[submit_station['train_no']] = datetime.datetime.now()
            else:
                print(u"未知错误 {0}".format("".join(getQueueCountResult)))
        return False

    #  模拟提交订单
    def checkQueueOrder(self, token, ticketInfoForPassengerForm, submit_station, is_node_code=False):
        """
       ，参数获取方法还是get_ticketInfoForPassengerForm 中获取
        :return:
        """
        passengerTicketStrList, oldPassengerStr = my_util.get_passenger_ticket_str(self.user_info, self.seat[submit_station['seat']]['type'])
        data = {"purpose_codes": ticketInfoForPassengerForm["purpose_codes"],
                "key_check_isChange": ticketInfoForPassengerForm["key_check_isChange"],
                "leftTicketStr": ticketInfoForPassengerForm["leftTicketStr"],
                "train_location": ticketInfoForPassengerForm["train_location"], "seatDetailType": "000",
                "roomType": "00", "dwAll": "N", "whatsSelect": 1, "_json_at": "", "REPEAT_SUBMIT_TOKEN": token,
                'passengerTicketStr': self.seat[submit_station['seat']]['type'] + "," + ",".join(
                    passengerTicketStrList).rstrip("_{0}".format(self.seat[submit_station['seat']]['type'])),
                'oldPassengerStr': "".join(oldPassengerStr)}
        try:
            if is_node_code:
                print(u"正在使用自动识别验证码功能")
                for i in range(3):
                    result = self._send(self.confUrl['codeImgByOrder'])
                    # 保存验证码图片到本地
                    img_path = './tkcode'
                    try:
                        print("下载验证码成功")
                        open(img_path, 'wb').write(result)
                    except OSError as e:
                        print(e)
                    # 识别验证码图片
                    rand_code = my_util.get_rand_code(self.configs['is_auto_code'], file_path=img_path)
                    rand_data = {
                        "randCode": rand_code,
                        "rand": "randp",
                        "_json_att": None,
                        "REPEAT_SUBMIT_TOKEN": token
                    }
                    fresult = self._send(self.confUrl["checkRandCodeAnsyn"], rand_data)  # 校验验证码是否正确
                    if  fresult['data']['msg'] == 'TRUE':
                        print(u"验证码通过,正在提交订单")
                        data['randCode'] = rand_code
                        break
                    else:
                        print (u"验证码有误, {0}次尝试重试".format(i+1))
                print(u"验证码超过限定次数3次，放弃此次订票机会!")
            else:
                print(u"不需要验证码")
            time.sleep(0.5)
            checkQueueOrderResult = self._send(self.confUrl["checkQueueOrderUrl"], data)
            if "status" in checkQueueOrderResult and checkQueueOrderResult["status"]:
                c_data = checkQueueOrderResult["data"] if "data" in checkQueueOrderResult else {}
                if 'submitStatus' in c_data and c_data['submitStatus'] is True:
                    print("提交订单成功！")
                    return True
                else:
                    if 'errMsg' in c_data and c_data['errMsg']:
                        print("提交订单失败，{0}".format(c_data['errMsg']))
                    else:
                        print(c_data)
                        print('订票失败!很抱歉,请重试提交预订功能!')
            elif "messages" in checkQueueOrderResult and checkQueueOrderResult["messages"]:
                print("提交订单失败,错误信息: " + checkQueueOrderResult["messages"])
            else:
                print("提交订单中，请耐心等待：" + checkQueueOrderResult["message"])
        except ValueError:
            print("接口 {0} 无响应".format(self.confUrl["checkQueueOrderUrl"]))
        return False

    # 排队获取订单等待信息
    def queryOrderWaitTime(self):
        """
        排队获取订单等待信息,每隔3秒请求一次，最高请求次数为30次！
        :return:
        """
        num = 1
        while True:
            _random = int(round(time.time() * 1000))
            num += 1
            if num > 30:
                print("超出排队时间，自动放弃，正在重新刷票")
                return False
            try:
                data = {"random": _random, "tourFlag": "dc"}
                queryOrderWaitTimeResult = self._send(self.confUrl["queryOrderWaitTimeUrl"], data)
            except ValueError:
                queryOrderWaitTimeResult = {}
            if queryOrderWaitTimeResult:
                if "status" in queryOrderWaitTimeResult and queryOrderWaitTimeResult["status"]:
                    if "orderId" in queryOrderWaitTimeResult["data"] and queryOrderWaitTimeResult["data"]["orderId"] is not None:
                        # 成功返回订单号
                        print("恭喜您订票成功，订单号为：{0}, 请立即打开浏览器登录12306，访问‘未完成订单’，在30分钟内完成支付！".format(
                            queryOrderWaitTimeResult["data"]["orderId"]))
                        return True, queryOrderWaitTimeResult["data"]["orderId"]
                    elif "msg" in queryOrderWaitTimeResult["data"] and queryOrderWaitTimeResult["data"]["msg"]:
                        print(queryOrderWaitTimeResult["data"]["msg"])
                        break
                    elif "waitTime"in queryOrderWaitTimeResult["data"] and queryOrderWaitTimeResult["data"]["waitTime"]:
                        print("排队等待时间预计还剩 {0} ms".format(0-queryOrderWaitTimeResult["data"]["waitTime"]))
                    else:
                        print ("正在等待中")
                elif "messages" in queryOrderWaitTimeResult and queryOrderWaitTimeResult["messages"]:
                    print("排队等待失败： " + queryOrderWaitTimeResult["messages"])
                else:
                    print("第{}次排队中,请耐心等待".format(num+1))
            else:
                print("排队中")
            time.sleep(2)

        else:
            print("订单提交失败！,正在重新刷票")
        return False

    # 订单列表页
    def initNoComplete(self):
        """
        获取订单前需要进入订单列表页，获取订单列表页session
        :return:
        """
        headers = {"Cookie": "acw_tc=AQAAAEnFJnekLwwAtGHjZZCr79B6dpXk; current_captcha_type=Z"}
        data = {"_json_att": ""}
        self._send(self.confUrl["initNoCompleteUrl"], data=data, headers=headers)

    # 获取未完成订单列表信息
    def queryMyOrderNoComplete(self):
        data = {"_json_att": ""}
        try:
            queryMyOrderNoCompleteResult = self._send(self.confUrl["queryMyOrderNoCompleteUrl"], data)
        except ValueError:
            queryMyOrderNoCompleteResult = {}
        if queryMyOrderNoCompleteResult:
            if "data" in queryMyOrderNoCompleteResult and queryMyOrderNoCompleteResult["data"] and "orderDBList" in queryMyOrderNoCompleteResult["data"] and queryMyOrderNoCompleteResult["data"]["orderDBList"]:
                order_id = queryMyOrderNoCompleteResult["data"]["orderDBList"][0]["sequence_no"]
                return order_id
            elif "data" in queryMyOrderNoCompleteResult and "orderCacheDTO" in queryMyOrderNoCompleteResult["data"] and queryMyOrderNoCompleteResult["data"]["orderCacheDTO"]:
                if "message" in queryMyOrderNoCompleteResult["data"]["orderCacheDTO"] and \
                        queryMyOrderNoCompleteResult["data"]["orderCacheDTO"]["message"]:
                    print(queryMyOrderNoCompleteResult["data"]["orderCacheDTO"]["message"]["message"])
            else:
                if "message" in queryMyOrderNoCompleteResult and queryMyOrderNoCompleteResult["message"]:
                    print(queryMyOrderNoCompleteResult["message"])
        else:
            print(u"接口 {0} 无响应".format(self.confUrl["queryMyOrderNoCompleteUrl"]))
        return False

    # 取消订单
    def cancelNoCompleteMyOrder(self, sequence_no):
        """
        取消订单
        :param sequence_no: 订单编号
        :return:
        """
        cancelNoCompleteMyOrderData = {
            "sequence_no": sequence_no,
            "cancel_flag": "cancel_order",
            "_json_att": ""
        }
        cancelNoCompleteMyOrderResult = self._send(self.confUrl["cancelNoCompleteMyOrder"], cancelNoCompleteMyOrderData)
        if "data" in cancelNoCompleteMyOrderResult and "existError" in cancelNoCompleteMyOrderResult["data"] and cancelNoCompleteMyOrderResult["data"]["existError"] == "N":
            print("排队超时，已为您自动取消订单，订单编号: {0}".format(sequence_no))
            time.sleep(2)
            return True
        else:
            print("排队超时，取消订单失败， 订单号{0}".format(sequence_no))
        return False

    # 登录验证码
    def verify_code(self, rand_code):
        """
        验证码校验
        :return:
        """
        codeCheckData = {
            "answer": rand_code,
            "rand": "sjrand",
            "login_site": "E"
        }
        result = self._send(self.confUrl["codeCheck"], codeCheckData)
        if "result_code" in result and result["result_code"] == "4":
            print("验证码通过,开始登录..")
            return True
        else:
            if "result_message" in result:
                print(result["result_message"])
            self.httpClient = httpClient()          # 重置httpClient

    # 执行流程
    def main(self):
        # 获取cdn
        cdn_util = cdnUtil.CDNProxy('kyfw.12306.cn')
        request_list = cdn_util.all_cdn()
        # 1.检查是否登录
        self.check_user()
        with futures.ThreadPoolExecutor(configCommon.poolSize) as executor:
            i = 0
            end = len(request_list)
            result = False
            num = 0
            while True:
                if time.strftime('%H:%M:%S', time.localtime(time.time())) > "23:00:00":
                    print("12306休息时间，本程序自动停止,明天早上6点将自动运行.{0}".format(datetime.datetime.now()))
                    time.sleep(60 * 60 * 7)
                time.sleep(1)
                # 2.开启线程检查cdn是否有票
                future_tasks = set()
                for q in range(configCommon.poolSize):
                    if i >= end:
                        i = 0
                    future = executor.submit(self.check_ticket, 'https://' + json.loads(request_list[i])['ip'])
                    future_tasks.add(future)
                    i = i + 1
                for f in futures.as_completed(future_tasks):
                    f_ret = f.result()
                    # print(f_ret)
                    # 3.有票主线程尝试下单
                    if f_ret['result']:
                        num += 1
                        self.check_user()                                          # 先检查登录
                        result, submit_station = self.buy_ticket(f_ret)                       # result 预约结果  submit_station 车次信息
                    if result:                      # 预约成功 - 提交联系人信息
                        initdc_url = self.confUrl["initdc_url"]
                        initdc_result = self._send(initdc_url)
                        token_name = re.compile(r"var globalRepeatSubmitToken = '(\S+)'")
                        ticketInfoForPassengerForm_name = re.compile(r'var ticketInfoForPassengerForm=(\{.+\})?')
                        # order_request_params_name = re.compile(r'var orderRequestDTO=(\{.+\})?')
                        token = re.search(token_name, initdc_result).group(1)
                        re_tfpf = re.findall(ticketInfoForPassengerForm_name, initdc_result)
                        # re_orp = re.findall(order_request_params_name, initdc_result)
                        if re_tfpf:
                            ticketInfoForPassengerForm = json.loads(re_tfpf[0].replace("'", '"'))
                        else:
                            print('ticketInfoForPassengerForm_name : ')
                            print(re_tfpf)
                            # continue
                        # if re_orp:
                        #     order_request_params = json.loads(re_orp[0].replace("'", '"'))
                            # print('order_request_params : ')
                            # print(order_request_params)
                        if self.user_info is None:
                            # 获取乘车人信息
                            self.user_info = self.getPassengerDTOs(token)
                        # 提交订单
                        order, is_need_code = self.checkOrderInfo(token, submit_station, self.user_info)
                        if order:
                            # 排队查询
                            if self.getQueueCount(token, ticketInfoForPassengerForm, submit_station):
                                # 模拟操作提交订单
                                if self.checkQueueOrder(token, ticketInfoForPassengerForm, submit_station, is_need_code):
                                    # 查询等待时间
                                    queryOrderWaitTimeResult, order_id = self.queryOrderWaitTime()
                                    if queryOrderWaitTimeResult:
                                        # 成功发送邮件
                                        my_util.send_email(self.configs['to_email'], '订票成功',
                                                           "恭喜您订票成功，订单号为：{0}, 请立即打开浏览器登录12306，访问‘未完成订单’，在30分钟内完成支付！".format(order_id),
                                                           self.configs['email_conf'])
                                        return True             # 订票成功直接结束
                                        # break
                                    else:
                                        # 排队失败，自动取消排队订单
                                        self.initNoComplete()                            # 进入订单列表页
                                        order_id = self.queryMyOrderNoComplete()         # 查询未完成订单
                                        if order_id:                                    # 和前面的order_id是一样的
                                            self.cancelNoCompleteMyOrder(order_id)      # 取消
                        result = False                                      # 预订失败
        #         if result or num == 6:
        #             break
        # print('result :' + self.host)
        # print()

    #检查用户是否登录
    def check_user(self):
        """检查用户是否达到订票条件"""
        data = {"_json_att": ""}
        check_user = self._send(self.confUrl["check_user_url"], data=data)
        print(check_user)
        check_user_flag = check_user['data']['flag']
        if check_user_flag is True:
            self.is_check_user["user_time"] = datetime.datetime.now()
        else:
            if check_user['messages']:
                print('用户检查失败：%s，可能未登录，可能session已经失效' % check_user['messages'][0])
                print('正在尝试重新登录')
                self.login()
                self.is_check_user["user_time"] = datetime.datetime.now()
            else:
                print('用户检查失败： %s，可能未登录，可能session已经失效' % check_user)
                print('正在尝试重新登录')
                self.login()
                self.is_check_user["user_time"] = datetime.datetime.now()

    # 发送请求
    def _send(self, urlconf, data=None, host=None, headers=None):
        if headers is not None:
            headers['Referer'] = urlconf['Referer']
            headers['Host'] = urlconf['Host']
        else:
            headers = {'Referer': urlconf['Referer'], 'Host': urlconf['Host']}
        if host is not None:
            headers['Host'] = host
        if urlconf['req_type'] == "post":
            result = self.httpClient.post(self.host + urlconf['req_url'], data, headers=headers)
        else:
            result = self.httpClient.get(self.host + urlconf['req_url'], headers=headers)
        # if urlconf['is_logger']:
        #     logger.log(
        #         "url: {0}\n入参: {1}\n请求方式: {2}\n".format(urlconf["req_url"], data, urlconf['req_type']))
        if urlconf['is_json']:
            # print("Json result:")
            # print(result)
            # logger.log("Json返回: {0}\n\n".format(result))
            result = json.loads(result)
        return result

    # uamauthclient
    def uamauthclient(self, uamtk):
        """
        登录成功后,显示用户名
        :return:
        """
        if not uamtk:
            return "权限校验码不能为空"
        else:
            data = {"tk": uamtk}
            uamauthclientResult = self._send(self.confUrl["uamauthclient"], data)
            if uamauthclientResult:
                if "result_code" in uamauthclientResult and uamauthclientResult["result_code"] == 0:
                    print("欢迎 {} 登录".format(uamauthclientResult["username"]))
                    return True
                else:
                    return False
            else:
                self._send(self.confUrl['getUserInfo'])


if __name__ == '__main__':
    # ssl._create_default_https_context = ssl._create_unverified_context
    votes = Votes()
    votes.main()

    # res = votes.httpClient.get('http://www.baidu.com')
    # device_list = [1, 2, 3, 4, 6]  # 需要处理的设备个数
    # task_pool = threadpool.ThreadPool(4)  # 8是线程池中线程的个数
    # request_list = []  # 存放任务列表
    # # 首先构造任务列表 args = ([],{})   ([device], {})
    # request_list = threadpool.makeRequests(ThreadFun, device_list, test)
    # # 将每个任务放到线程池中，等待线程池中线程各自读取任务，然后进行处理，
    # [task_pool.putRequest(req) for req in request_list]
    # # 等待所有任务处理完成，则返回，如果没有处理完，T则一直阻塞
    # task_pool.wait()
    pass





