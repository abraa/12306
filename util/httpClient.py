import os
import socket
from urllib import request, parse, error
from util import my_util
import json
from http import cookiejar


class httpClient(object):
    req = None
    header = None
    cj = None

    def __init__(self):
        self.header = self._set_header()
        # 自动记住cookie
        self._cookies()
        pass

    def get(self, url, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, **kw):

        if ('headers' in kw):
            headers = {**self.header, **kw.get('headers')}
        else:
            headers = self.header
            # 发起请求
        self.req = request.Request(url, headers=headers)
        # 设置请求配置
        # self._get_config()
        if('proxy' in kw):
           self._proxy(kw.get('proxy'))
        # page = request.urlopen(self.req)
        # html = page.read()
        # print(html)
        # print(html.decode("utf-8"))
        # return html.decode("utf-8")
        return self._send(timeout=timeout)

    def post(self, url, data, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, **kw):
        if('headers' in kw):
            headers = {**self.header, **kw.get('headers')}
        else:
            headers = self.header
            headers["Content-Length"] = "{0}".format(len(data))
        # 发起请求
        self.req = request.Request(url, headers=headers)
        # 设置请求配置
        # self._get_config()
        if ('proxy' in kw):
            self._proxy(kw.get('proxy'))
        data = parse.urlencode(data).encode('utf-8')
        return self._send(data=data, timeout=timeout)

    def _send(self, data=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, **kw):
        try:
            if self.cj is None:
                self._cookies()
            self.cj.add_cookie_header(self.req)
            opener = request.build_opener(request.HTTPCookieProcessor(self.cj))
            page = opener.open(self.req, data=data, timeout=timeout)
            try:
                # page = request.urlopen(self.req, data=data)
                html = page.read()
                html = html.decode("utf-8")
            except UnicodeDecodeError:
                pass
            finally:
                    page.close()
        except error.HTTPError as e:
            print('HTTPError: ')
            print(e.code())
            print(e.read().decode('utf-8'))
        except socket.timeout as e:
            return ""
        return html

    def _set_header(self):
        """设置header"""
        return {
            'Accept-Language': 'zh-CN,zh;q = 0.9',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'If-Modified-Since': '0',
            'Pragma': 'no-cache',
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "X-Requested-With": "xmlHttpRequest",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36",
            # "Referer": "https://kyfw.12306.cn/otn/login/init",
            "Accept": "*/*",
            # 'Cookie':'JSESSIONID=6EB2FE776D38259CEBD8C7A811E6C75F;_jc_save_wfdc_flag=dc; _jc_save_fromDate=2018-03-02;_jc_save_fromStation=%u5E7F%u5DDE%2CGZQ;_jc_save_toStation=%u90B5%u4E1C%2CFIQ; _jc_save_toDate=2018-02-24;route=c5c62a339e7744272a54643b3be5bf64;BIGipServerotn=1977155850.50210.0000; BIGipServerpassport=1005060362.50215.0000'
            # 'Cookie':'JSESSIONID=0C426D36DFD97151A7DAC94D68C10A07; _jc_save_fromStation=%u5E7F%u5DDE%2CGZQ; _jc_save_wfdc_flag=dc; _jc_save_toStation=%u6B66%u6C49%2CWHN; route=495c805987d0f5c8c84b14f60212447d; BIGipServerotn=2715222282.24610.0000; _jc_save_fromDate=2018-03-14; _jc_save_toDate=2018-03-05'
            }

    def _get_config(self, filename=os.path.dirname(__file__)+'/../config/curlConf.ini', **kw):
        res = my_util.read_conf(filename)
        if 'header' in res:
            for key, value in res.get('header').items():
                self.req.add_header(key, value)

    def set_config(self, filename=os.path.dirname(__file__)+'/../config/curlConf.ini', **kw):
        my_util.create_conf(filename, **kw)

    def _proxy(self, proxy):
        for key, value in proxy.items():
            self.req.set_proxy(value, key)

    def _cookies(self):
        self.cj = cookiejar.CookieJar()

#
# res = httpClient().get('http://www.whatismyip.com.tw', proxy={'http': '61.155.164.111:3128'})

# res = eval(res+'.decode("utf-8")')
# print(json.loads(res))

# obj = {'header': {'Referer': 'https://zhidao.baidu.com/', 'Host': 'zhidao.baidu.com', "X-Forwarded-For": "1"}}
# client =httpClient()
# client.set_config(**obj)
# client.get('https://zhidao.baidu.com/ichat/api/chatlist')