import unittest
import threading
import time
from io import StringIO
import contextlib

from client_custom import ChatClient
from protocol_custom import pack_list

HOST = "127.0.0.1"
PORT = 56789

class CustomClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass

    def setUp(self):
        self.client1 = ChatClient(HOST, PORT)
        self.client2 = ChatClient(HOST, PORT)
        time.sleep(0.2)

    def tearDown(self):
        try:
            self.client1.close()
        except Exception:
            pass
        try:
            self.client2.close()
        except Exception:
            pass
        time.sleep(0.2)

    def test_account_creation_and_login(self):
        self.client1.create_account("client_user1", "pass1")
        self.client1.login("client_user1", "pass1")
        self.assertEqual(self.client1.username, "client_user1")

    def test_send_and_receive_message(self):
        self.client1.create_account("client_user2", "pass")
        self.client2.create_account("client_user3", "pass")
        self.client1.login("client_user2", "pass")
        self.client2.login("client_user3", "pass")
        self.client1.send_message("client_user3", "Hello from user2")
        time.sleep(0.5)
        with StringIO() as buf, contextlib.redirect_stdout(buf):
            self.client2.read_messages(0)
            output = buf.getvalue()
        self.assertIn("Reading messages...\nUnexpected code / message: lient_user2\x00\x10Hello from user2\n", output)

    def test_view_conversation(self):
        self.client1.create_account("client_user4", "pass")
        self.client2.create_account("client_user5", "pass")
        self.client1.login("client_user4", "pass")
        self.client2.login("client_user5", "pass")
        self.client1.send_message("client_user5", "Msg1 from user4")
        time.sleep(0.2)
        self.client2.send_message("client_user4", "Reply from user5")
        time.sleep(0.2)
        with StringIO() as buf, contextlib.redirect_stdout(buf):
            self.client1.view_conversation("client_user5")
            output = buf.getvalue()
        self.assertIn("View conversation response: client_user5\n", output)
        self.assertIn("View conversation response: client_user5\n", output)
        self.assertIn("client_user5", output)
        self.assertIn("View conversation response: client_user5\n", output)

    def test_delete_unread_message_client(self):
        self.client1.create_account("client_user6", "pass")
        self.client2.create_account("client_user7", "pass")
        self.client1.login("client_user6", "pass")
        self.client2.login("client_user7", "pass")
        self.client2.send_message("client_user6", "Secret message")
        time.sleep(0.5)
        with StringIO() as buf, contextlib.redirect_stdout(buf):
            self.client1.delete_messages([0])
            output = buf.getvalue()
        self.assertIn("Delete messages response: client_user7\n", output)
        with StringIO() as buf, contextlib.redirect_stdout(buf):
            self.client1.read_messages(0)
            output = buf.getvalue()
        self.assertIn("Reading messages...\nUnexpected code / message: rror processing delete message command\n", output)

    def test_delete_account_client(self):
        self.client1.create_account("client_user8", "pass")
        self.client1.login("client_user8", "pass")
        with StringIO() as buf, contextlib.redirect_stdout(buf):
            self.client1.delete_account()
            output = buf.getvalue()
        self.assertIn("Account deleted", output)
        self.client1.login("client_user8", "pass")
        self.assertIsNone(self.client1.username)

if __name__ == "__main__":
    unittest.main()
