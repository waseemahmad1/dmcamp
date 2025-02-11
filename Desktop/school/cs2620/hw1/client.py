import socket
import json
import threading
import time
import sys
import os
import datetime

# Maximum message buffer size
MSGLEN = 409600

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def create_msg(cmd, src="", to="", body="", extra_fields=None):

    msg = {
        "cmd": cmd,
        "from": src,
        "to": to,
        "body": body
    }

    if extra_fields and isinstance(extra_fields, dict):
        msg.update(extra_fields)
    return (json.dumps(msg) + "\n").encode()

class ChatClient:
    def __init__(self, server_host, server_port):
        self.server_host = server_host
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((server_host, server_port))
        self.username = None
        self.login_err = False

    def login(self, username, password):
        if self.username is None:
            msg = create_msg("login", src=username, extra_fields={"password": password})
            self.sock.sendall(msg)
        else:
            eprint("You already logged in")

    def create_account(self, username, password):
        msg = create_msg("create", src=username, extra_fields={"password": password})
        self.sock.sendall(msg)

    def send_message(self, recipient, message):
        if not self.username:
            eprint("Please log in or create an account first")
        else:
            self.sock.sendall(create_msg("send", src=self.username, to=recipient, body=message))

    def list_accounts(self, wildcard):
        self.sock.sendall(create_msg("list", src=self.username, body=wildcard))

    def receive_messages(self, limit=""):
        # 'limit' can be blank (deliver all) or a number as a string.
        self.sock.sendall(create_msg("deliver", src=self.username, body=str(limit)))

    def delete_messages(self, indices):
        # Accept indices as a list or a comma-separated string.
        if isinstance(indices, list):
            indices_str = ",".join(str(i) for i in indices)
        else:
            indices_str = str(indices)
        self.sock.sendall(create_msg("delete_msg", src=self.username, body=indices_str))

    def delete_account(self):
        self.sock.sendall(create_msg("delete", src=self.username))

    def log_off(self):
        self.sock.sendall(create_msg("logoff", src=self.username))
        self.username = None

    def close(self):
        self.sock.sendall(create_msg("close", src=self.username))
        self.sock.close()

# Interactive system (currently only in terminal)

def handle_user():
    while True:
        if not client.username:
            print("\nAvailable commands:")
            print("0. Login")
            print("1. Create an account")
            print("2. Exit")
            choice = input("Enter a command number (0-2): ")
            if choice == "0":
                username = input("Enter your username: ")
                password = input("Enter your password: ")
                client.login(username, password)
                # Wait a short while for login response (avoid busy waiting)
                while not client.username:
                    if client.login_err:
                        client.login_err = False
                        break
                    time.sleep(0.1)
            elif choice == "1":
                username = input("Enter the username to create: ")
                password = input("Enter your password: ")
                client.create_account(username, password)
            elif choice == "2":
                client.close()
                os._exit(0)
            else:
                print("Invalid command. Please try again.")
        else:
            print("\nAvailable commands:")
            print("0. Send a message")
            print("1. Deliver undelivered messages")
            print("2. List accounts")
            print("3. Delete individual messages")
            print("4. Delete account")
            print("5. Log off")
            choice = input("Enter a command number (0-5): ")
            if choice == "0":
                recipient = input("Enter the recipient's username: ")
                message = input("Enter the message: ")
                print(datetime.datetime.now())
                client.send_message(recipient, message)
            elif choice == "1":
                limit = input("Enter number of messages to read (leave blank for all): ")
                client.receive_messages(limit)
            elif choice == "2":
                wildcard = input("Enter a matching wildcard (optional, default '*'): ")
                client.list_accounts(wildcard)
            elif choice == "3":
                indices = input("Enter message indices to delete (comma separated): ")
                client.delete_messages(indices)
            elif choice == "4":
                client.delete_account()
            elif choice == "5":
                client.log_off()
            else:
                print("Invalid command. Please try again.")

def handle_message():
    buffer = ""
    while True:
        try:
            data = client.sock.recv(MSGLEN).decode()
        except Exception as e:
            eprint("Error receiving data:", e)
            break
        if not data:
            break
        buffer += data
        # Process complete messages delimited by newline
        while "\n" in buffer:
            msg_str, buffer = buffer.split("\n", 1)
            if not msg_str:
                continue
            try:
                msg = json.loads(msg_str)
            except json.JSONDecodeError:
                eprint("Received invalid JSON")
                continue

            cmd = msg.get("cmd", "")
            if cmd == "login":
                if msg.get("error", False):
                    client.login_err = True
                    print("Failed to login: {}. Please try again.".format(msg.get("body", "")))
                else:
                    print("Logged in successfully. {}".format(msg.get("body", "")))
                    client.username = msg.get("to", "")
            elif cmd == "deliver":
                print("{} sent: {}".format(msg.get("from", ""), msg.get("body", "")))
                print(datetime.datetime.now())
            elif cmd == "create":
                if msg.get("error", False):
                    print("Failed to create account: {}. Please try again.".format(msg.get("body", "")))
                else:
                    print("Account created successfully. {}".format(msg.get("body", "")))
            elif cmd == "delete":
                if msg.get("error", False):
                    print("Failed to delete account: {}. Please try again.".format(msg.get("body", "")))
                else:
                    print("Account deleted successfully.")
                    client.username = None
            elif cmd == "delete_msg":
                if msg.get("error", False):
                    print("Failed to delete messages: {}. Please try again.".format(msg.get("body", "")))
                else:
                    print("Specified messages deleted successfully.")
            elif cmd == "list":
                print("Matching accounts:")
                print(msg.get("body", ""))
            elif cmd == "send":
                if msg.get("error", False):
                    print("Failed to send message: {}. Please try again.".format(msg.get("body", "")))
                else:
                    print(msg.get("body", ""))
            elif cmd == "logoff":
                print(msg.get("body", "Logged off"))
            else:
                print("Received:", msg)
    client.sock.close()


PORT = 56789
host_ip = input("Enter host ip address: ")
client = ChatClient(host_ip, PORT)

# Run the user interface and message-handling threads
threading.Thread(target=handle_user, daemon=True).start()
threading.Thread(target=handle_message, daemon=True).start()

# Prevent the main thread from exiting
while True:
    time.sleep(1)