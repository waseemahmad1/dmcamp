import socket
import json
import threading
import time
import sys
import os
import datetime

MSGLEN = 409600  # Maximum message length for socket communication

# Print error messages to stderr
def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

# Create a JSON message with a command and optional fields
def create_msg(cmd, src="", to="", body="", extra_fields=None):
    msg = {
        "cmd": cmd,
        "from": src,
        "to": to,
        "body": body
    }
    if extra_fields and isinstance(extra_fields, dict):
        msg.update(extra_fields)
    # Append newline as a delimiter and encode the message to bytes
    return (json.dumps(msg) + "\n").encode()

class ChatClient:
    def __init__(self, server_host, server_port):
        self.server_host = server_host
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((server_host, server_port))
        self.username = None
        self.login_err = False  # Flag to track login errors

    # Send a login request with username and password
    def login(self, username, password):
        if self.username is None:
            msg = create_msg("login", src=username, extra_fields={"password": password})
            self.sock.sendall(msg)
        else:
            eprint("You already logged in")

    # Send a request to create a new account
    def create_account(self, username, password):
        msg = create_msg("create", src=username, extra_fields={"password": password})
        self.sock.sendall(msg)

    # Send a message to a specified recipient
    def send_message(self, recipient, message):
        if not self.username:
            eprint("Please log in or create an account first")
        else:
            self.sock.sendall(create_msg("send", src=self.username, to=recipient, body=message))

    # Request a list of accounts that match a wildcard pattern
    def list_accounts(self, wildcard):
        self.sock.sendall(create_msg("list", src=self.username, body=wildcard))

    # Request to read a specified number of undelivered messages
    def read_messages(self, limit=""):
        self.sock.sendall(create_msg("read", src=self.username, body=str(limit)))

    # Request deletion of messages by their indices
    def delete_messages(self, indices):
        if isinstance(indices, list):
            indices_str = ",".join(str(i) for i in indices)
        else:
            indices_str = str(indices)
        self.sock.sendall(create_msg("delete_msg", src=self.username, body=indices_str))

    # Request to view the conversation with a specific user
    def view_conversation(self, other_user):
        self.sock.sendall(create_msg("view_conv", src=self.username, to=other_user))

    # Request deletion of the current account
    def delete_account(self):
        self.sock.sendall(create_msg("delete", src=self.username))

    # Log off from the current session
    def log_off(self):
        self.sock.sendall(create_msg("logoff", src=self.username))
        self.username = None

    # Close the connection to the server
    def close(self):
        self.sock.sendall(create_msg("close", src=self.username))
        self.sock.close()

# Function to handle user commands from the terminal interactively
def handle_user():
    while True:
        if not client.username:
            print("\nAvailable commands:")
            print("1. Login")
            print("2. Create an account")
            print("3. Exit")
            choice = input("Enter a command number (1-3): ")
            if choice == "1":
                username = input("Enter your username: ")
                password = input("Enter your password: ")
                client.login(username, password)
                # Wait for login confirmation
                while not client.username:
                    if client.login_err:
                        client.login_err = False
                        break
                    time.sleep(0.1)
            elif choice == "2":
                username = input("Enter the username to create: ")
                password = input("Enter your password: ")
                client.create_account(username, password)
            elif choice == "3":
                client.close()
                os._exit(0)
            else:
                print("Invalid command. Please try again.")
        else:
            print("\nAvailable commands:")
            print("1. Send a message")
            print("2. Read undelivered messages")
            print("3. List accounts")
            print("4. Delete individual messages")
            print("5. Delete account")
            print("6. Log off")
            print("7. View conversation with a user")
            choice = input("Enter a command number (1-7): ")
            if choice == "1":
                recipient = input("Enter the recipient's username: ")
                message = input("Enter the message: ")
                print(datetime.datetime.now())
                client.send_message(recipient, message)
            elif choice == "2":
                limit = input("Enter number of messages to read (leave blank for all): ")
                client.read_messages(limit)
            elif choice == "3":
                wildcard = input("Enter a matching wildcard (optional, default '*'): ")
                client.list_accounts(wildcard)
            elif choice == "4":
                indices = input("Enter message indices to delete (comma separated): ")
                client.delete_messages(indices)
            elif choice == "5":
                client.delete_account()
            elif choice == "6":
                client.log_off()
            elif choice == "7":
                other_user = input("Enter the username to view conversation with: ")
                client.view_conversation(other_user)
            else:
                print("Invalid command. Please try again.")

# Function to handle incoming messages from the server
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

        # Process each complete JSON message (delimited by newline)
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
            # Handle login response
            if cmd == "login":
                if msg.get("error", False):
                    client.login_err = True
                    print("Failed to login: {}. Please try again.".format(msg.get("body", "")))
                else:
                    print("Logged in successfully. {}".format(msg.get("body", "")))
                    client.username = msg.get("to", "")
            # Handle read messages response
            elif cmd == "read":
                try:
                    parsed = json.loads(msg.get("body", ""))
                    if isinstance(parsed, list):
                        display_text = "Unread Messages:\n"
                        for m in parsed:
                            if isinstance(m, dict):
                                msg_id = m.get("id", m.get("index", "N/A"))
                                sender = m.get("sender", "Unknown")
                                message_text = m.get("message", "")
                                display_text += f"[ID {msg_id}] {sender}: {message_text}\n"
                            else:
                                display_text += f"{m}\n"
                        print(display_text)
                    else:
                        sender = msg.get("from", "Unknown")
                        print(f"{sender}: {msg.get('body', '')}")
                except Exception as e:
                    sender = msg.get("from", "Unknown")
                    print(f"{sender}: {msg.get('body', '')}")
            # Handle account creation response
            elif cmd == "create":
                if msg.get("error", False):
                    print("Failed to create account: {}. Please try again.".format(msg.get("body", "")))
                else:
                    print("Account created successfully. {}".format(msg.get("body", "")))
            # Handle account deletion response
            elif cmd == "delete":
                if msg.get("error", False):
                    print("Failed to delete account: {}. Please try again.".format(msg.get("body", "")))
                else:
                    print("Account deleted successfully.")
                    client.username = None
            # Handle delete messages response
            elif cmd == "delete_msg":
                if msg.get("error", False):
                    print("Failed to delete messages: {}. Please try again.".format(msg.get("body", "")))
                else:
                    print("Specified messages deleted successfully.")
            # Handle list accounts response
            elif cmd == "list":
                print("Matching accounts:")
                print(msg.get("body", ""))
            # Handle send message response
            elif cmd == "send":
                if msg.get("error", False):
                    print("Failed to send message: {}. Please try again.".format(msg.get("body", "")))
                else:
                    print(msg.get("body", ""))
            # Handle view conversation response
            elif cmd == "view_conv":
                try:
                    conv = json.loads(msg.get("body", ""))
                    display_text = "Conversation:\n"
                    for m in conv:
                        display_text += f"[ID {m['id']}] {m['sender']} ({m['timestamp']}): {m['message']}\n"
                    print(display_text)
                except Exception as e:
                    print(f"Error parsing conversation history: {e}")
            # Handle logoff response
            elif cmd == "logoff":
                print(msg.get("body", "Logged off"))
            else:
                print("Received:", msg)
    client.sock.close()

if __name__ == '__main__':
    # Default host and port values
    PORT = 12345
    HOST = "127.0.0.1"
    client = ChatClient(HOST, PORT)

    # Start threads for handling user input and incoming messages concurrently
    threading.Thread(target=handle_user, daemon=True).start()
    threading.Thread(target=handle_message, daemon=True).start()

    # Keep the main thread alive
    while True:
        time.sleep(1)
