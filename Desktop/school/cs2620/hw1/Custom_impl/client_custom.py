import socket
import struct
import threading
import sys
from protocol_custom import (
    CMD_LOGIN, CMD_CREATE, CMD_SEND, CMD_READ, CMD_DELETE_MSG,
    CMD_VIEW_CONV, CMD_DELETE_ACC, CMD_LOGOFF, CMD_CLOSE,
    CMD_CHAT, CMD_LIST, CMD_READ_ACK,
    encode_message, decode_message,
    pack_short_string, pack_long_string,
    unpack_short_string, unpack_long_string
)

# Helper functions for packing data for each command
def pack_login(username, password):
    # Pack username and password into a login payload
    return pack_short_string(username) + pack_short_string(password)

def pack_create(username, password):
    # Pack username and password for account creation
    return pack_short_string(username) + pack_short_string(password)

def pack_send(sender, recipient, message):
    # Pack sender recipient and message into a payload
    return pack_short_string(sender) + pack_short_string(recipient) + pack_long_string(message)

def pack_read(username, limit):
    # Pack username and a 1 byte limit 0 means read all messages
    return pack_short_string(username) + struct.pack("!B", limit)

def pack_delete_msg(username, indices):
    # Pack username and a list of indices of messages to delete
    data = pack_short_string(username)
    data += struct.pack("!B", len(indices))
    for idx in indices:
        data += struct.pack("!B", idx)
    return data

def pack_view_conv(username, other_user):
    # Pack username and the other user to view conversation
    return pack_short_string(username) + pack_short_string(other_user)

def pack_delete_acc(username):
    # Pack username for account deletion
    return pack_short_string(username)

def pack_logoff(username):
    # Pack username for logging off
    return pack_short_string(username)

def pack_close(username):
    # Pack username for closing the connection
    return pack_short_string(username)

# Chatclient class handles client server communication
class ChatClient:
    def __init__(self, host, port):
        # Create and connect the socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self.username = None 

    def login(self, username, password):
        # build and send the login payload
        payload = pack_login(username, password)
        self.sock.sendall(encode_message(CMD_LOGIN, payload))
        cmd, data = decode_message(self.sock)
        resp, _ = unpack_short_string(data, 0)
        # Update username if login is successful
        if "successful" in resp:
            self.username = username
        print("login response", resp)

    def create_account(self, username, password):
        # Build and send the account creation payload
        payload = pack_create(username, password)
        self.sock.sendall(encode_message(CMD_CREATE, payload))
        cmd, data = decode_message(self.sock)
        resp, _ = unpack_short_string(data, 0)
        print("create account response", resp)

    def list_accounts(self, wildcard="*"):
        # Use a helper function to pack the wildcard
        payload = pack_list(wildcard)
        self.sock.sendall(encode_message(CMD_LIST, payload))
        cmd, data = decode_message(self.sock)
        # If the server returned a long string response for the list unpack and display matching accounts
        if cmd == CMD_LIST:
            resp, _ = unpack_long_string(data, 0)
            print("matching accounts", resp)
        else:
            resp, _ = unpack_short_string(data, 0)
            print("list error", resp)

    def send_message(self, recipient, message):
        # Check if user is logged in before sending a message
        if not self.username:
            print("please login first")
            return
        payload = pack_send(self.username, recipient, message)
        self.sock.sendall(encode_message(CMD_SEND, payload))
        cmd, data = decode_message(self.sock)
        resp, _ = unpack_short_string(data, 0)
        print("send message response", resp)

    def read_messages(self, limit=0):
        # Check if user is logged in before reading messages
        if not self.username:
            print("please login first")
            return
        payload = pack_read(self.username, limit)
        self.sock.sendall(encode_message(CMD_READ, payload))
        print("reading messages")
        # Loop until a non read message is received
        while True:
            cmd, data = decode_message(self.sock)
            if cmd != CMD_READ:
                msg_text, _ = unpack_long_string(data, 0)
                if msg_text == "NO_MESSAGES":
                    print("no new messages")
                elif msg_text == "END_OF_MESSAGES":
                    print("finished reading messages")
                else:
                    print("unexpected code  message", msg_text)
                break
            offset = 0
            sender, offset = unpack_short_string(data, offset)
            msg_text, offset = unpack_long_string(data, offset)
            print("from", sender, ":", msg_text)
        # Send an acknowledgement after finishing reading messages
        ack_payload = pack_short_string("DONE")
        self.sock.sendall(encode_message(CMD_READ_ACK, ack_payload))

    def delete_messages(self, indices):
        # Check if user is logged in before deleting messages
        if not self.username:
            print("please login first")
            return
        payload = pack_delete_msg(self.username, indices)
        self.sock.sendall(encode_message(CMD_DELETE_MSG, payload))
        cmd, data = decode_message(self.sock)
        resp, _ = unpack_short_string(data, 0)
        print("delete messages response", resp)

    def view_conversation(self, other_user):
        # Check if the user is logged in before viewing a conversation
        if not self.username:
            print("please login first")
            return
        payload = pack_view_conv(self.username, other_user)
        self.sock.sendall(encode_message(CMD_VIEW_CONV, payload))
        cmd, data = decode_message(self.sock)
        if cmd == CMD_VIEW_CONV:
            conv_str, _ = unpack_long_string(data, 0)
            print("conversation", conv_str)
        else:
            resp, _ = unpack_short_string(data, 0)
            print("view conversation response", resp)

    def delete_account(self):
        # Delete the currently logged in account
        if not self.username:
            print("please login first")
            return
        payload = pack_delete_acc(self.username)
        self.sock.sendall(encode_message(CMD_DELETE_ACC, payload))
        cmd, data = decode_message(self.sock)
        resp, _ = unpack_short_string(data, 0)
        print("delete account response", resp)
        if "deleted" in resp.lower():
            self.username = None

    def log_off(self):
        # Log off from the server
        if not self.username:
            print("not logged in")
            return
        payload = pack_logoff(self.username)
        self.sock.sendall(encode_message(CMD_LOGOFF, payload))
        cmd, data = decode_message(self.sock)
        resp, _ = unpack_short_string(data, 0)
        print("log off response", resp)
        self.username = None

    def close(self):
        # Close the connection to the server
        uname = self.username if self.username else ""
        payload = pack_close(uname)
        self.sock.sendall(encode_message(CMD_CLOSE, payload))
        self.sock.close()

def client_main():
    # Ask user for server host and port
    host = input("enter server host ")
    port = int(input("enter server port "))
    client = ChatClient(host, port)

    while True:
        if client.username is None:
            print("\nmenu")
            print("1 create account")
            print("2 login")
            print("3 close")
            choice = input("choose an option ")
            if choice == "1":
                uname = input("enter username ")
                pw = input("enter password ")
                client.create_account(uname, pw)
            elif choice == "2":
                uname = input("enter username ")
                pw = input("enter password ")
                client.login(uname, pw)
            elif choice == "3":
                client.close()
                break
            else:
                print("invalid choice please login first")
        else:
            print("\nmenu")
            print("1 list accounts")
            print("2 send message")
            print("3 read messages")
            print("4 delete messages")
            print("5 view conversation")
            print("6 delete account")
            print("7 log off")
            print("8 close")
            choice = input("choose an option ")
            if choice == "1":
                pattern = input("enter wildcard pattern default * ") or "*"
                client.list_accounts(pattern)
            elif choice == "2":
                rec = input("recipient username ")
                msg = input("message ")
                client.send_message(rec, msg)
            elif choice == "3":
                limit = input("enter number of messages to read 0 for all ")
                try:
                    limit = int(limit)
                except:
                    limit = 0
                client.read_messages(limit)
            elif choice == "4":
                idx_str = input("enter indices to delete comma separated ")
                idx_list = [int(x.strip()) for x in idx_str.split(",") if x.strip().isdigit()]
                client.delete_messages(idx_list)
            elif choice == "5":
                ou = input("enter other user's name ")
                client.view_conversation(ou)
            elif choice == "6":
                client.delete_account()
            elif choice == "7":
                client.log_off()
            elif choice == "8":
                client.close()
                break
            else:
                print("invalid choice")

if __name__ == "__main__":
    client_main()
