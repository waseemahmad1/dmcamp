import unittest
import threading
import time
import json
import socket
from server import ChatServer
from client import ChatClient

MSGLEN = 409600
HOST = '127.0.0.1'
PORT = 56789

def read_json(client, timeout=2):
    client.sock.settimeout(timeout)
    data = ""
    try:
        while "\n" not in data:
            data += client.sock.recv(MSGLEN).decode()
    except socket.timeout:
        pass
    client.sock.settimeout(None)
    return json.loads(data.strip())

def login_and_set_username(client, username, password):
    client.login(username, password)
    resp = read_json(client)
    if resp.get("cmd") == "login" and not resp.get("error", False):
        client.username = username
    return resp

class TestChatClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ChatServer(host=HOST, port=PORT)
        cls.server_thread = threading.Thread(target=cls.server.start, daemon=True)
        cls.server_thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.server_thread.join(timeout=1)

    def test_create_account(self):
        client = ChatClient(HOST, PORT)
        client.create_account("test_user_create", "pass")
        resp = read_json(client)
        self.assertIn("Account created", resp.get("body", ""))
        client.close()

    def test_duplicate_account(self):
        username = "test_user_dup"
        client1 = ChatClient(HOST, PORT)
        client1.create_account(username, "pass")
        resp1 = read_json(client1)
        self.assertIn("Account created", resp1.get("body", ""))
        client1.close()
        client2 = ChatClient(HOST, PORT)
        client2.create_account(username, "pass")
        resp2 = read_json(client2)
        self.assertTrue(resp2.get("error", False))
        self.assertIn("already exists", resp2.get("body", "").lower())
        client2.close()

    def test_login(self):
        client = ChatClient(HOST, PORT)
        username = "test_user_login"
        client.create_account(username, "pass")
        _ = read_json(client)
        resp = login_and_set_username(client, username, "pass")
        self.assertIn("Login successful", resp.get("body", ""))
        self.assertEqual(resp.get("to"), username)
        client.close()

    def test_failed_login(self):
        client = ChatClient(HOST, PORT)
        username = "test_user_failed"
        client.create_account(username, "pass")
        _ = read_json(client)
        client.login(username, "wrong")
        resp = read_json(client)
        self.assertTrue(resp.get("error", False))
        self.assertIn("incorrect", resp.get("body", "").lower())
        client.close()

    def test_list_accounts(self):
        for uname in ["test_list1", "test_list2", "test_list3"]:
            tmp = ChatClient(HOST, PORT)
            tmp.create_account(uname, "pass")
            _ = read_json(tmp)
            tmp.close()
        client = ChatClient(HOST, PORT)
        client.create_account("test_list_master", "pass")
        _ = read_json(client)
        login_and_set_username(client, "test_list_master", "pass")
        client.list_accounts("test_list*")
        resp = read_json(client)
        body = resp.get("body", "")
        for uname in ["test_list1", "test_list2", "test_list3"]:
            self.assertIn(uname, body)
        client.close()

    def test_send_and_read_message(self):
        sender = ChatClient(HOST, PORT)
        receiver = ChatClient(HOST, PORT)
        sender_username = "test_sender"
        receiver_username = "test_receiver"
        sender.create_account(sender_username, "pass")
        _ = read_json(sender)
        receiver.create_account(receiver_username, "pass")
        _ = read_json(receiver)
        login_and_set_username(sender, sender_username, "pass")
        login_and_set_username(receiver, receiver_username, "pass")
        sender.send_message(receiver_username, "Hello receiver!")
        time.sleep(0.2)
        resp = read_json(receiver)
        self.assertEqual(resp.get("cmd"), "chat")
        payload = json.loads(resp.get("body", "[]"))
        self.assertGreater(len(payload), 0)
        self.assertIn("Hello receiver!", payload[0].get("message", ""))
        sender.close()
        receiver.close()

    def test_read_messages_offline(self):
        sender = ChatClient(HOST, PORT)
        receiver = ChatClient(HOST, PORT)
        sender_username = "test_offline_sender"
        receiver_username = "test_offline_receiver"
        sender.create_account(sender_username, "pass")
        _ = read_json(sender)
        receiver.create_account(receiver_username, "pass")
        _ = read_json(receiver)
        login_and_set_username(sender, sender_username, "pass")
        sender.send_message(receiver_username, "Offline message")
        time.sleep(0.2)
        login_and_set_username(receiver, receiver_username, "pass")
        receiver.read_messages("")
        resp = read_json(receiver)
        unread = json.loads(resp.get("body", "[]"))
        self.assertGreaterEqual(len(unread), 1)
        self.assertIn("Offline message", unread[0].get("message", ""))
        sender.close()
        receiver.close()

    def test_log_off(self):
        client = ChatClient(HOST, PORT)
        username = "test_logoff"
        client.create_account(username, "pass")
        _ = read_json(client)
        login_and_set_username(client, username, "pass")
        client.log_off()
        resp = read_json(client)
        self.assertIn("logged off", resp.get("body", "").lower())
        client.close()

    def test_close(self):
        client = ChatClient(HOST, PORT)
        username = "test_close"
        client.create_account(username, "pass")
        _ = read_json(client)
        login_and_set_username(client, username, "pass")
        client.close()
        with self.assertRaises(Exception):
            client.send_message("anyone", "test")
    
if __name__ == '__main__':
    unittest.main()
