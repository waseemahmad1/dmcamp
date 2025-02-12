import unittest
import socket
import json
import threading
import time
import re
from io import StringIO
import contextlib
import struct
from server import ChatServer

MSGLEN = 409600
TEST_HOST = '127.0.0.1'
TEST_PORT = 56789

class TestChatServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ChatServer(host=TEST_HOST, port=TEST_PORT)
        cls.server_thread = threading.Thread(target=cls.server.start, daemon=True)
        cls.server_thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.server_thread.join(timeout=1)

    def recv_json(sock):
        buffer = ""
        while "\n" not in buffer:
            chunk = sock.recv(MSGLEN).decode()
            if not chunk:
                break
            buffer += chunk
        line, _ = buffer.split("\n", 1)
        return json.loads(line)

    def send_and_recv(self, msg_dict):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((TEST_HOST, TEST_PORT))
        s.sendall((json.dumps(msg_dict) + "\n").encode())
        data = ""
        while "\n" not in data:
            data += s.recv(MSGLEN).decode()
        s.close()
        return json.loads(data.strip())

    def test_create_account(self):
        msg = {"cmd": "create", "from": "user1", "to": "", "body": "", "password": "pass1"}
        resp = self.send_and_recv(msg)
        self.assertIn("Account created", resp.get("body", ""))
        resp_dup = self.send_and_recv(msg)
        self.assertTrue(resp_dup.get("error", False))
        self.assertIn("already exists", resp_dup.get("body", "").lower())

    def test_login(self):
        msg_create = {"cmd": "create", "from": "user2", "to": "", "body": "", "password": "pass2"}
        self.send_and_recv(msg_create)
        msg_login = {"cmd": "login", "from": "user2", "to": "", "body": "", "password": "pass2"}
        resp_login = self.send_and_recv(msg_login)
        self.assertIn("Login successful", resp_login.get("body", ""))
        msg_bad_login = {"cmd": "login", "from": "user2", "to": "", "body": "", "password": "wrongpass"}
        resp_bad = self.send_and_recv(msg_bad_login)
        self.assertTrue(resp_bad.get("error", False))
        self.assertIn("incorrect password", resp_bad.get("body", "").lower())
        s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s1.connect((TEST_HOST, TEST_PORT))
        s1.sendall((json.dumps(msg_login) + "\n").encode())
        time.sleep(0.1)
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s2.connect((TEST_HOST, TEST_PORT))
        s2.sendall((json.dumps(msg_login) + "\n").encode())
        data = ""
        while "\n" not in data:
            data += s2.recv(MSGLEN).decode()
        resp_dup = json.loads(data.strip())
        self.assertTrue(resp_dup.get("error", False))
        self.assertIn("already logged in elsewhere", resp_dup.get("body", "").lower())
        s1.sendall((json.dumps({"cmd": "logoff", "from": "user2", "to": "", "body": ""}) + "\n").encode())
        s1.close()
        s2.close()

    def test_list_accounts(self):
        for username in ["user3", "user4"]:
            msg_create = {"cmd": "create", "from": username, "to": "", "body": "", "password": "pass"}
            self.send_and_recv(msg_create)
        msg_list = {"cmd": "list", "from": "user3", "to": "", "body": "user*"}
        resp_list = self.send_and_recv(msg_list)
        body = resp_list.get("body", "")
        self.assertIn("user3", body)
        self.assertIn("user4", body)

    def test_send_and_read_message(self):
        for username, password in [("sender", "pass"), ("receiver", "pass")]:
            msg_create = {"cmd": "create", "from": username, "to": "", "body": "", "password": password}
            self.send_and_recv(msg_create)
        receiver_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        msg_login_receiver = {"cmd": "login", "from": "receiver", "to": "", "body": "", "password": "pass"}
        receiver_sock.connect((TEST_HOST, TEST_PORT))
        receiver_sock.sendall((json.dumps(msg_login_receiver) + "\n").encode())
        data = ""
        while "\n" not in data:
            data += receiver_sock.recv(MSGLEN).decode()
        sender_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        msg_login_sender = {"cmd": "login", "from": "sender", "to": "", "body": "", "password": "pass"}
        sender_sock.connect((TEST_HOST, TEST_PORT))
        sender_sock.sendall((json.dumps(msg_login_sender) + "\n").encode())
        data_sender = ""
        while "\n" not in data_sender:
            data_sender += sender_sock.recv(MSGLEN).decode()
        msg_send = {"cmd": "send", "from": "sender", "to": "receiver", "body": "Hello Receiver!"}
        sender_sock.sendall((json.dumps(msg_send) + "\n").encode())
        data_receiver = ""
        while "\n" not in data_receiver:
            data_receiver += receiver_sock.recv(MSGLEN).decode()
        resp_chat = json.loads(data_receiver.strip())
        self.assertEqual(resp_chat.get("cmd"), "chat")
        payload = json.loads(resp_chat.get("body", "[]"))
        self.assertEqual(payload[0]["message"], "Hello Receiver!")
        sender_sock.sendall((json.dumps({"cmd": "logoff", "from": "sender", "to": "", "body": ""}) + "\n").encode())
        receiver_sock.sendall((json.dumps({"cmd": "logoff", "from": "receiver", "to": "", "body": ""}) + "\n").encode())
        sender_sock.close()
        receiver_sock.close()

    def test_send_to_offline_and_read(self):
        for username, password in [("offline_sender", "pass"), ("offline_receiver", "pass")]:
            msg_create = {"cmd": "create", "from": username, "to": "", "body": "", "password": password}
            self.send_and_recv(msg_create)
        sender_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        msg_login_sender = {"cmd": "login", "from": "offline_sender", "to": "", "body": "", "password": "pass"}
        sender_sock.connect((TEST_HOST, TEST_PORT))
        sender_sock.sendall((json.dumps(msg_login_sender) + "\n").encode())
        data_sender = ""
        while "\n" not in data_sender:
            data_sender += sender_sock.recv(MSGLEN).decode()
        msg_send = {"cmd": "send", "from": "offline_sender", "to": "offline_receiver", "body": "Hello Offline!"}
        sender_sock.sendall((json.dumps(msg_send) + "\n").encode())
        data_send_resp = ""
        while "\n" not in data_send_resp:
            data_send_resp += sender_sock.recv(MSGLEN).decode()
        resp_send = json.loads(data_send_resp.strip())
        self.assertIn("Message sent", resp_send.get("body", ""))
        sender_sock.sendall((json.dumps({"cmd": "logoff", "from": "offline_sender", "to": "", "body": ""}) + "\n").encode())
        sender_sock.close()
        receiver_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        msg_login_receiver = {"cmd": "login", "from": "offline_receiver", "to": "", "body": "", "password": "pass"}
        receiver_sock.connect((TEST_HOST, TEST_PORT))
        receiver_sock.sendall((json.dumps(msg_login_receiver) + "\n").encode())
        data_receiver = ""
        while "\n" not in data_receiver:
            data_receiver += receiver_sock.recv(MSGLEN).decode()
        msg_read = {"cmd": "read", "from": "offline_receiver", "to": "", "body": ""}
        receiver_sock.sendall((json.dumps(msg_read) + "\n").encode())
        data_read = ""
        while "\n" not in data_read:
            data_read += receiver_sock.recv(MSGLEN).decode()
        resp_read = json.loads(data_read.strip())
        unread = json.loads(resp_read.get("body", "[]"))
        self.assertGreaterEqual(len(unread), 1)
        self.assertEqual(unread[0]["message"], "Hello Offline!")
        receiver_sock.sendall((json.dumps({"cmd": "logoff", "from": "offline_receiver", "to": "", "body": ""}) + "\n").encode())
        receiver_sock.close()

    def test_delete_message_and_view_conv(self):
        for username, password in [("conv_user1", "pass"), ("conv_user2", "pass")]:
            msg_create = {"cmd": "create", "from": username, "to": "", "body": "", "password": password}
            self.send_and_recv(msg_create)
        user1_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        msg_login_u1 = {"cmd": "login", "from": "conv_user1", "to": "", "body": "", "password": "pass"}
        user1_sock.connect((TEST_HOST, TEST_PORT))
        user1_sock.sendall((json.dumps(msg_login_u1) + "\n").encode())
        while True:
            data = user1_sock.recv(MSGLEN).decode()
            if "\n" in data:
                break
        user2_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        msg_login_u2 = {"cmd": "login", "from": "conv_user2", "to": "", "body": "", "password": "pass"}
        user2_sock.connect((TEST_HOST, TEST_PORT))
        user2_sock.sendall((json.dumps(msg_login_u2) + "\n").encode())
        while True:
            data = user2_sock.recv(MSGLEN).decode()
            if "\n" in data:
                break
        msg_send1 = {"cmd": "send", "from": "conv_user1", "to": "conv_user2", "body": "Hello from conv_user1"}
        user1_sock.sendall((json.dumps(msg_send1) + "\n").encode())
        data_chat = ""
        while "\n" not in data_chat:
            data_chat += user2_sock.recv(MSGLEN).decode()
        msg_send2 = {"cmd": "send", "from": "conv_user2", "to": "conv_user1", "body": "Hello from conv_user2"}
        user2_sock.sendall((json.dumps(msg_send2) + "\n").encode())
        data_chat2 = ""
        while "\n" not in data_chat2:
            data_chat2 += user1_sock.recv(MSGLEN).decode()
        msg_view = {"cmd": "view_conv", "from": "conv_user1", "to": "conv_user2", "body": ""}
        user1_sock.sendall((json.dumps(msg_view) + "\n").encode())
        data_conv = ""
        while "\n" not in data_conv:
            data_conv += user1_sock.recv(MSGLEN).decode()
        first_line = data_conv.strip().split("\n")[0]
        resp_conv = json.loads(first_line)
        conv_history = json.loads(resp_conv.get("body", "[]"))
        self.assertGreaterEqual(len(conv_history), 1)
        msg_id_to_delete = conv_history[0]["id"]
        msg_delete = {"cmd": "delete_msg", "from": "conv_user1", "to": "", "body": str(msg_id_to_delete)}
        user1_sock.sendall((json.dumps(msg_delete) + "\n").encode())
        user1_sock.sendall((json.dumps(msg_view) + "\n").encode())
        data_conv2 = ""
        while "\n" not in data_conv2:
            data_conv2 += user1_sock.recv(MSGLEN).decode()
        first_line_conv2 = data_conv2.strip().split("\n")[0]
        resp_conv2 = json.loads(first_line_conv2)
        conv_history2 = json.loads(resp_conv2.get("body", "[]"))
        ids = [msg["id"] for msg in conv_history2]
        self.assertNotIn(msg_id_to_delete, [1])
        user1_sock.sendall((json.dumps({"cmd": "logoff", "from": "conv_user1", "to": "", "body": ""}) + "\n").encode())
        user2_sock.sendall((json.dumps({"cmd": "logoff", "from": "conv_user2", "to": "", "body": ""}) + "\n").encode())
        user1_sock.close()
        user2_sock.close()

    def test_delete_account(self):
        username = "delete_user"
        msg_create = {"cmd": "create", "from": username, "to": "", "body": "", "password": "pass"}
        self.send_and_recv(msg_create)
        msg_delete = {"cmd": "delete", "from": username, "to": "", "body": ""}
        resp_delete = self.send_and_recv(msg_delete)
        self.assertIn("Account deleted", resp_delete.get("body", ""))
        msg_login = {"cmd": "login", "from": username, "to": "", "body": "", "password": "pass"}
        resp_login = self.send_and_recv(msg_login)
        self.assertTrue(resp_login.get("error", False))
        self.assertIn("does not exist", resp_login.get("body", "").lower())

    def test_logoff_and_close(self):
        username = "logoff_user"
        msg_create = {"cmd": "create", "from": username, "to": "", "body": "", "password": "pass"}
        self.send_and_recv(msg_create)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        msg_login = {"cmd": "login", "from": username, "to": "", "body": "", "password": "pass"}
        s.connect((TEST_HOST, TEST_PORT))
        s.sendall((json.dumps(msg_login) + "\n").encode())
        data = ""
        while "\n" not in data:
            data += s.recv(MSGLEN).decode()
        msg_logoff = {"cmd": "logoff", "from": username, "to": "", "body": ""}
        s.sendall((json.dumps(msg_logoff) + "\n").encode())
        data_logoff = ""
        while "\n" not in data_logoff:
            data_logoff += s.recv(MSGLEN).decode()
        resp_logoff = json.loads(data_logoff.strip())
        self.assertIn("logged off", resp_logoff.get("body", "").lower())
        msg_close = {"cmd": "close", "from": username, "to": "", "body": ""}
        s.sendall((json.dumps(msg_close) + "\n").encode())
        s.close()

if __name__ == '__main__':
    unittest.main()
