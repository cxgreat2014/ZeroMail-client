import os
import websocket
import re
from json import loads, dumps
from requests import get
import execjs


class ZeroMail:
    __version__ == 0.1
    def __init__(self, host='127.0.0.1', port=43110, address='Mail.ZeroNetwork.bit', port_control='http',
                 data_file='data.json'):
        html = get(f'{port_control}://{host}:{port}/{address}/', headers={"ACCEPT": "text/html"}).content.decode()
        self.wrapper_key = re.search('wrapper_key = "([a-z0-9]+)', html).group(1)
        self.link = f"ws://{host}:{port}/Websocket?wrapper_key={self.wrapper_key}"
        self.id = 0
        self.ws = websocket.create_connection(self.link)
        self.send('channelJoin', {"channel": "siteChanged"}, 1000000)
        self.send('siteInfo', {})
        self.site_info = self.recv_json()
        self.auth_address = self.site_info['auth_address']

        # ToDo: Load cache && config
        '''
        if os.path.isfile(data_file):
            self.config = loads(data_file)
        else:
            self.config = {}
        if 'scanned' not in self.config:
            self.config['scanned'] = False
        if not self.config['scanned']:
            self.my_mail = self.scan_mails()
        '''
        self.recv_mail = self.scan_mails()

    def send(self, cmd, params=None, id=0):
        if params is None:
            params = ""
        message = {'cmd': cmd, 'params': params}
        if id == 0:
            self.id += 1
            message['id'] = self.id
        else:
            message['id'] = id
        message = dumps(message)
        self.ws.send(message)

    def recv(self):
        return self.ws.recv()

    def recv_json(self):
        return loads(self.recv())['result']

    def get_sent_mail(self):
        self.send('fileGet', {"inner_path": f"data/users/{self.auth_address}/data.json", "required": False})
        return self.recv_json()

    def get_mailbox_info(self):
        self.send("fileRules", f"data/users/{self.auth_address}/data.json")
        return self.recv_json()

    def get_user_id_by_auth_address(self, auth_address_list):
        self.send("dbQuery", ["SELECT directory, value AS cert_user_id\nFROM json\nLEFT JOIN keyvalue USING (json_id)"
                              "\nWHERE ? AND file_name = 'content.json' AND key = 'cert_user_id'",
                              {"directory": auth_address_list}])
        return self.recv_json()

    def get_mail(self):
        return self.recv_mail

    def scan_mails(self):
        self.send("dbQuery", ["SELECT * FROM secret\nLEFT JOIN json USING (json_id)\n\nORDER BY date_added ASC"])
        secret_list = self.recv_json()
        self.send("eciesDecrypt", [[mail['encrypted'] for mail in secret_list]])
        result = self.recv_json()
        contacts = [[secret_list[x]['directory'], result[x]] for x in range(len(secret_list)) if result[x] is not None]
        print(contacts)
        address_book = self.get_user_id_by_auth_address([x[0] for x in contacts])
        address_book = {x['directory']: x['cert_user_id'] for x in address_book}
        self.send("dbQuery", [
            f"SELECT * FROM message\nLEFT JOIN json USING (json_id)\nWHERE directory IN ({repr([x[0] for x in contacts])[1:-1]})\nORDER BY date_added ASC"])
        mails = self.recv_json()
        self.send("aesDecrypt", [[x['encrypted'].split(',') for x in mails], [x[1] for x in contacts]])
        result = self.recv_json()
        recv_mail = []
        for x in range(len(result)):
            if result[x] is not None:
                mail = loads(repr(execjs.eval(f"decodeURIComponent(escape('{result[x]}'))"))[1:-1])
                mail['from'] = f"{mails[x]['directory']}<{address_book[mails[x]['directory']]}>"
                recv_mail.append(mail.copy())
        mails = None
        return recv_mail


if __name__ == "__main__":
    mails = ZeroMail().recv_mail
    for mail in mails:
        print('#' * 36)
        print('Subject: ' + mail['subject'])
        print('From: ' + mail['from'])
        print('Message: ' + mail['body'])
