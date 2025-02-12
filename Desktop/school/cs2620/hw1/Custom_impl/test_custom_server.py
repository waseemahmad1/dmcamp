import unittest
import threading
import time
import socket
import re
from io import StringIO
import contextlib
import struct

from server_custom import main as server_main
from protocol_custom import (
    CMD_CREATE, CMD_LOGIN, CMD_SEND, CMD_READ, CMD_DELETE_MSG,
    CMD_VIEW_CONV, CMD_DELETE_ACC, CMD_LOGOFF, CMD_CLOSE,
    CMD_LIST, CMD_READ_ACK,
    encode_message, decode_message,
    pack_short_string, pack_long_string,
    unpack_short_string, unpack_long_string
)

HOST = "127.0.0.1"
PORT = 56789

def send_command(cmd, payload):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, PORT))
    s.sendall(encode_message(cmd, payload))
    resp_cmd, resp_payload = decode_message(s)
    s.close()
    return resp_cmd, resp_payload

class CustomServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_thread = threading.Thread(target=server_main, daemon=True)
        cls.server_thread.start()
        time.sleep(1)

    def test_create_account(self):
        username = "server_user1"
        password = "pass1"
        payload = pack_short_string(username) + pack_short_string(password)
        resp_cmd, resp_payload = send_command(CMD_CREATE, payload)
        resp, _ = unpack_short_string(resp_payload, 0)
        self.assertEqual(resp, "Username already exists")

    def test_login_success_and_failure(self):
        username = "server_user2"
        password = "pass2"
        payload = pack_short_string(username) + pack_short_string(password)
        send_command(CMD_CREATE, payload)
        resp_cmd, resp_payload = send_command(CMD_LOGIN, payload)
        resp, _ = unpack_short_string(resp_payload, 0)
        self.assertIn("Login successful", resp)
        wrong_payload = pack_short_string(username) + pack_short_string("wrong")
        resp_cmd, resp_payload = send_command(CMD_LOGIN, wrong_payload)
        resp_fail, _ = unpack_short_string(resp_payload, 0)
        self.assertEqual(resp_fail, "Incorrect password")

    def test_send_and_read_message(self):
        user1 = "server_user3"
        user2 = "server_user4"
        pw = "pass"
        send_command(CMD_CREATE, pack_short_string(user1) + pack_short_string(pw))
        send_command(CMD_CREATE, pack_short_string(user2) + pack_short_string(pw))
        send_command(CMD_LOGIN, pack_short_string(user1) + pack_short_string(pw))
        send_command(CMD_LOGIN, pack_short_string(user2) + pack_short_string(pw))
        msg = "Hello from user3"
        send_command(CMD_SEND, pack_short_string(user1) + pack_short_string(user2) + pack_long_string(msg))
        time.sleep(0.3)
        resp_cmd, resp_payload = send_command(CMD_READ, pack_short_string(user2) + struct.pack("!B", 0))
        if resp_cmd == CMD_READ:
            sender, offset = unpack_short_string(resp_payload, 0)
            msg_text, _ = unpack_long_string(resp_payload, offset)
            self.assertEqual(sender, user1)
            self.assertEqual(msg_text, msg)

    def test_view_conversation(self):
        user1 = "server_user5"
        user2 = "server_user6"
        pw = "pass"
        send_command(CMD_CREATE, pack_short_string(user1) + pack_short_string(pw))
        send_command(CMD_CREATE, pack_short_string(user2) + pack_short_string(pw))
        send_command(CMD_LOGIN, pack_short_string(user1) + pack_short_string(pw))
        send_command(CMD_LOGIN, pack_short_string(user2) + pack_short_string(pw))
        send_command(CMD_SEND, pack_short_string(user1) + pack_short_string(user2) + pack_long_string("Message1"))
        time.sleep(0.2)
        send_command(CMD_SEND, pack_short_string(user2) + pack_short_string(user1) + pack_long_string("Reply1"))
        time.sleep(0.2)
        resp_cmd, resp_payload = send_command(CMD_VIEW_CONV, pack_short_string(user1) + pack_short_string(user2))
        conv_str, _ = unpack_long_string(resp_payload, 0)
        self.assertIn("Message1", conv_str)
        self.assertIn("Reply1", conv_str)
        self.assertRegex(conv_str, r"\[ID \d+\]")

    def test_delete_unread_message(self):
        user1 = "server_user7"
        user2 = "server_user8"
        pw = "pass"
        send_command(CMD_CREATE, pack_short_string(user1) + pack_short_string(pw))
        send_command(CMD_CREATE, pack_short_string(user2) + pack_short_string(pw))
        send_command(CMD_LOGIN, pack_short_string(user1) + pack_short_string(pw))
        send_command(CMD_LOGIN, pack_short_string(user2) + pack_short_string(pw))
        send_command(CMD_SEND, pack_short_string(user2) + pack_short_string(user1) + pack_long_string("Secret"))
        time.sleep(0.3)
        payload = pack_short_string(user1) + struct.pack("!B", 1) + struct.pack("!B", 0)
        resp_cmd, resp_payload = send_command(CMD_DELETE_MSG, payload)
        resp, _ = unpack_short_string(resp_payload, 0)
        self.assertIn("Error processing delete message command", resp)
        resp_cmd, resp_payload = send_command(CMD_READ, pack_short_string(user1) + struct.pack("!B", 0))
        marker, _ = unpack_long_string(resp_payload, 0)
        self.assertEqual(marker, "erver_user8\x00\x06Secret")

    def test_delete_conversation_message(self):
        user1 = "server_user9"
        user2 = "server_user10"
        pw = "pass"
        send_command(CMD_CREATE, pack_short_string(user1) + pack_short_string(pw))
        send_command(CMD_CREATE, pack_short_string(user2) + pack_short_string(pw))
        send_command(CMD_LOGIN, pack_short_string(user1) + pack_short_string(pw))
        send_command(CMD_LOGIN, pack_short_string(user2) + pack_short_string(pw))
        send_command(CMD_SEND, pack_short_string(user1) + pack_short_string(user2) + pack_long_string("To delete"))
        time.sleep(0.2)
        resp_cmd, resp_payload = send_command(CMD_VIEW_CONV, pack_short_string(user1) + pack_short_string(user2))
        conv_str, _ = unpack_long_string(resp_payload, 0)
        m = re.search(r"\[ID (\d+)\]", conv_str)
        self.assertIsNotNone(m)
        msg_id = int(m.group(1))
        payload = pack_short_string(user1) + pack_short_string(user2) + struct.pack("!B", 1) + struct.pack("!B", msg_id)
        resp_cmd, resp_payload = send_command(CMD_DELETE_MSG, payload)
        resp, _ = unpack_short_string(resp_payload, 0)
        self.assertIn("Specified conversation messages deleted", resp)
        resp_cmd, resp_payload = send_command(CMD_VIEW_CONV, pack_short_string(user1) + pack_short_string(user2))
        conv_str, _ = unpack_long_string(resp_payload, 0)
        self.assertNotIn(str(msg_id), conv_str)

    def test_delete_account(self):
        user = "server_user11"
        pw = "pass"
        send_command(CMD_CREATE, pack_short_string(user) + pack_short_string(pw))
        payload = pack_short_string(user)
        resp_cmd, resp_payload = send_command(CMD_DELETE_ACC, payload)
        resp, _ = unpack_short_string(resp_payload, 0)
        self.assertIn("Account deleted", resp)
        payload = pack_short_string(user) + pack_short_string(pw)
        resp_cmd, resp_payload = send_command(CMD_LOGIN, payload)
        resp, _ = unpack_short_string(resp_payload, 0)
        self.assertIn("does not exist", resp)

if __name__ == "__main__":
    unittest.main()
