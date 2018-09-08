# encoding= 'utf8'
import configparser
import json
import os
import smtplib
from email.header import Header
from email.mime.text import MIMEText

from PIL import Image

from exception.PassengerUserException import PassengerUserException
from util import httpClient
from util.ruokuai import RClient


def read_conf(filename):
    # 读取配置文件 {section: {key: value}, ...}
    conf = configparser.ConfigParser()
    res = {}
    try:
        conf.read(filename)
    except IOError:
        return None
    secs = conf.sections()
    for i in secs:
        res[i] = {}
        options = conf.options(i)
        for key in options:
            res[i][key] = conf.get(i, key)
    return res


# 添加到配置 {section: {key: value}, ...}
def add_conf(filename, **kw):
    conf = configparser.ConfigParser()
    try:
        conf.read(filename)
    except IOError:
        pass
    for i, item in kw.items():
        if (not conf.has_section(i)):
            conf.add_section(i)
        for key, value in item.items():
            conf.set(i, key, value)
    fp = open(filename, 'w')
    conf.write(fp)
    fp.close()


# 生成新的配置文件
def create_conf(filename, **kw):
    try:
        os.remove(filename)
    except FileNotFoundError:
        pass
    add_conf(filename, **kw)


# 识别验证码
def get_rand_code(is_auto_code, file_path=None):
    """
    识别验证码
     1.调用PIL显示图片
    2.图片位置说明，验证码图片中每个图片代表一个下标，依次类推，1，2，3，4，5，6，7，8
    3.控制台输入对应下标，按照英文逗号分开，即可手动完成打码，
    :return: 坐标
    """
    try:
        # 是否自动登录 -- 自动打码
        if is_auto_code:
            print('is_auto_code')
            # 调用接口返回验证码值 (Ruokuai接口)
            rc = RClient(configs['ruokuai_account']["username"], configs['ruokuai_account']["pwd"])
            im = open(file_path, 'rb').read()
            Result = rc.rk_create(im, 6113)
            print(Result) 
            if "Result" in Result:
                return codexy(offset_str=",".join(list(Result["Result"])), is_raw_input=False)
            else:
                if "Error" in Result and Result["Error"]:
                    print("RClient.Error: ")
                    print(Result["Error"])
                    # raise Exception(Result["Error"])
            return ""
        else:
            img = Image.open(file_path)
            img.show()
            return codexy()
    except:
        pass


# 手动输入验证码
def codexy(offset_str=None, is_raw_input=True):
    """
    获取验证码
    :return: str
    """
    if is_raw_input:
        offset_str = input(u"请输入验证码: ")
    select = offset_str.split(',')
    post = []
    offsetsX = 0  # 选择的答案的left值,通过浏览器点击8个小图的中点得到的,这样基本没问题
    offsetsY = 0  # 选择的答案的top值
    for ofset in select:
        if ofset == '1':
            offsetsY = 44
            offsetsX = 44
        elif ofset == '2':
            offsetsY = 45
            offsetsX = 105
        elif ofset == '3':
            offsetsY = 46
            offsetsX = 174
        elif ofset == '4':
            offsetsY = 43
            offsetsX = 250
        elif ofset == '5':
            offsetsY = 109
            offsetsX = 46
        elif ofset == '6':
            offsetsY = 112
            offsetsX = 110
        elif ofset == '7':
            offsetsY = 114
            offsetsX = 181
        elif ofset == '8':
            offsetsY = 111
            offsetsX = 252
        else:
            pass
        post.append(offsetsX)
        post.append(offsetsY)
    randCode = str(post).replace(']', '').replace('[', '').replace("'", '').replace(' ', '')
    print("验证码识别坐标为{0}".format(randCode))
    return randCode


# 生成车站中文:简称对应表
def station_name(file='./station_name'):
    res = httpClient.httpClient().get(
        'https://kyfw.12306.cn/otn/resources/js/framework/station_name.js?station_version=1.9047')
    result = res.split("'")[1]  # 去掉引号前后.只保留内容
    # result = '@bjb|北京北|VAP|beijingbei|bjb|0@bjd|北京东|BOP|beijingdong|bjd|1@bji|北京|BJP|beijing|bj|2@bjn|北京南|VNP|beijingnan|bjn|3'
    result = result.split('@')
    result.pop(0)
    data = {}
    for i in result:
        res = i.split('|')
        data[res[1]] = res[2]
    with open(file, 'w+') as f:
        f.write(json.dumps(data))


# 读取车站中文:简称对应表返回json
def read_station(file='./station_name'):
    with open(file, 'r') as f:
        return json.loads(f.read())


# 返回12306座位提交对应值
def read_seat():
    return {
            '商务座': {'seat': 32, 'type': 9},
            '一等座': {'seat': 31, 'type': 'M'},
            '二等座': {'seat': 30, 'type': 'O'},
            '特等座': {'seat': 25, 'type': 'P'},
            '软卧': {'seat': 23, 'type': 4},
            '硬卧': {'seat': 28, 'type': 3},
            '硬座': {'seat': 29, 'type': 1},
            '无座': {'seat': 26, 'type': 1}
            }


# 拼装12306提交车次乘车人内容格式
def get_passenger_ticket_str(user_info, set_type):
    """
    获取提交车次人内容格式
    passengerTicketStr:O,0,1,乘客名称,1,4305211991020XXXX,,N_O,0,1,乘客名称2,1,43052719920118XXXX,,N
    oldPassengerStr: 乘客名称,1,430521199102068496,1_乘客名称,1,430521199102068496,1
    :return:
    """
    passengerTicketStrList = []
    oldPassengerStr = []
    if not user_info:
        print("联系人不在列表中，请查证后添加")
        raise PassengerUserException("联系人不在列表中，请查证后添加")
    if len(user_info) is 1:
        passengerTicketStrList.append(
            '0,' + user_info[0]['passenger_type'] + "," + user_info[0][
                "passenger_name"] + "," +
            user_info[0]['passenger_id_type_code'] + "," + user_info[0]['passenger_id_no'] + "," +
            user_info[0]['mobile_no'] + ',N')
        oldPassengerStr.append(
            user_info[0]['passenger_name'] + "," + user_info[0]['passenger_id_type_code'] + "," +
            user_info[0]['passenger_id_no'] + "," + user_info[0]['passenger_type'] + '_')
    else:
        for i in range(len(user_info)):
            passengerTicketStrList.append(
                '0,' + user_info[i]['passenger_type'] + "," + user_info[i][
                    "passenger_name"] + "," + user_info[i]['passenger_id_type_code'] + "," + user_info[i][
                    'passenger_id_no'] + "," + user_info[i]['mobile_no'] + ',N_' + set_type)
            oldPassengerStr.append(
                user_info[i]['passenger_name'] + "," + user_info[i]['passenger_id_type_code'] + "," +
                user_info[i]['passenger_id_no'] + "," + user_info[i]['passenger_type'] + '_')
    return passengerTicketStrList, oldPassengerStr


def send_email(to_email, subject, content, configs, from_email=None):
    if from_email is None:
        from_email = configs['username']

    message = MIMEText(content, 'html', 'utf-8')
    message['From'] = Header(from_email, 'utf-8')
    message['To'] = Header(to_email, 'utf-8')
    message['Subject'] = Header(subject, 'utf-8')
    try:
        smtpObj = smtplib.SMTP_SSL()
        smtpObj.connect(configs['host'], configs['port'])
        smtpObj.login(configs['username'], configs['password'])
        smtpObj.sendmail(from_email, to_email, message.as_string())
        smtpObj.close()
        print("邮件发送成功")
    except smtplib.SMTPException:
        print("Error: 无法发送邮件")

