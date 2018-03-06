# encoding=utf8
import collections
import json
import re
from concurrent import futures

from config import urlConf
from util.httpClient import httpClient


class CDNProxy:
    def __init__(self, host=None, file_path="./cdn_list"):
        self.host = host
        self.urlConf = urlConf.urls
        self.httpClint = httpClient()
        self.city_list = ['524906a3-2749-4469-aee3-48885f042a32', '38522b83-8893-4ca6-b45f-b6588b034462', '4ac18165-4d45-4c89-92f5-66bc6facf377']
        self.timeout = 5
        self.file_path = file_path
        self.headers = {
            'Host': 'ping.chinaz.com',
            'Origin': 'http://ping.chinaz.com',
            'Pragma': 'no-cache',
            'Referer': 'http://ping.chinaz.com'
        }



    def get_city_id(self):
        """
        获取所有城市md5参数
        :return:
        """
        if self.host:
            while True:
                url = self.urlConf["cdn_host"]["req_url"]
                data = {"host": self.host, "lintType": "电信,多线,联通,移动"}
                rep = self.httpClint.post(url, data, timeout=self.timeout, headers=self.headers)
                city_re = re.compile(r"<li id=\"(\S+)\" class=\"PingListCent PingRLlist")
                self.city_list = re.findall(city_re, rep)
                if self.city_list:
                    print(self.city_list)
                    break

    def open_cdn_file(self):
        f = open(self.file_path, "a+")
        return f

    def get_cdn_list(self):
        """
        筛选代理
        :return:
        """
        f = self.open_cdn_file()
        url = self.urlConf["cdn_list"]["req_url"]
        num = 1
        f.seek(0)
        f.truncate()
        future_tasks = set()
        with futures.ThreadPoolExecutor(10) as executor:
            for guid in self.city_list:
                data = {"guid": guid,
                        "host": "kyfw.12306.cn",
                        "ishost": 0,
                        "encode": "Eije8XUjdz7r0Jdr2zC01MpBcD3ObICD",
                        "checktype": 0}

                param = {'timeout': self.timeout, 'headers':self.headers}
                future = executor.submit(httpClient().post, url, data, **param)
                future_tasks.add(future)
            try:
                for future in futures.as_completed(future_tasks):
                    cdn_info = future.result()
                    if cdn_info:
                        split_cdn = cdn_info.split("(")[1].rstrip(")").replace("{", "").replace("}", "").split(",")
                        local_dict = collections.OrderedDict()
                        for i in split_cdn:
                            splits = i.split(":")
                            if splits[0] == "result":
                                local_dict[splits[1]] = splits[2].strip("'") if isinstance(splits[2], str) else splits[2]
                            else:
                                local_dict[splits[0]] = splits[1].strip("'") if isinstance(splits[1], str) else splits[1]
                        if local_dict and "state" in local_dict and local_dict["state"] == "1":
                            if "responsetime" in local_dict and local_dict["responsetime"].find("毫秒") != -1 and int(re.sub("\D", "", local_dict["responsetime"])) < 100:
                                f.write(json.dumps(local_dict)+"\n")
                                num += 1
            except Exception:
                pass
            finally:
                f.close()
        print(u"本次cdn获取完成，总个数{0}".format(num))

    def all_cdn(self):
        """获取cdn列表"""
        with open(self.file_path, 'r') as f:
            cdn = f.readlines()
            return cdn




if __name__ == '__main__':
    # print(a.rstrip("'"))
    cdn = CDNProxy('kyfw.12306.cn')
    cdn.get_city_id()
    cdn.get_cdn_list()
    # cdn.par_csv()
