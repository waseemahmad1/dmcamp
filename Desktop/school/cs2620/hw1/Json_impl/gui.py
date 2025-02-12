import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import threading
import socket
import json
import time
import datetime
import sys

PORT = 12345
MSGLEN = 409600

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

def parse_msg(raw_msg):
    try:
        return json.loads(raw_msg)
    except json.JSONDecodeError:
        return None

# Chat Client Class
class ChatClient:
    def __init__(self, server_host, server_port):
        self.server_host = server_host
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((server_host, server_port))
        self.username = None
        self.running = True

    def send_message(self, msg):
        self.sock.sendall((json.dumps(msg) + "\n").encode())

    def close(self):
        self.running = False
        self.sock.close()

    def receive_loop(self, callback):
        buffer = ""
        while self.running:
            try:
                data = self.sock.recv(MSGLEN).decode()
            except Exception as e:
                print("Error receiving data:", e, file=sys.stderr)
                break
            if not data:
                break
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if line:
                    msg = parse_msg(line)
                    if msg:
                        callback(msg)
        self.close()

# Tkinter GUI Class
class ChatGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("Chat Client")
        self.client = None
        self.user_list = []  # Will store the list of available users

        # Create three frames: login_frame, chat_frame, command_frame.
        self.login_frame = tk.Frame(master)
        self.chat_frame = tk.Frame(master)
        self.command_frame = tk.Frame(master)

        self.setup_login_frame()
        self.setup_chat_frame()
        self.setup_command_frame()

        self.login_frame.pack()

    def setup_login_frame(self):
        tk.Label(self.login_frame, text="Server IP:").grid(row=0, column=0, sticky="e")
        self.server_ip_entry = tk.Entry(self.login_frame)
        self.server_ip_entry.insert(0, "127.0.0.1")  # default for testing
        self.server_ip_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(self.login_frame, text="Username:").grid(row=1, column=0, sticky="e")
        self.username_entry = tk.Entry(self.login_frame)
        self.username_entry.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(self.login_frame, text="Password:").grid(row=2, column=0, sticky="e")
        self.password_entry = tk.Entry(self.login_frame, show="*")
        self.password_entry.grid(row=2, column=1, padx=5, pady=5)

        self.login_button = tk.Button(self.login_frame, text="Login", command=self.login)
        self.login_button.grid(row=3, column=0, padx=5, pady=5)

        self.create_button = tk.Button(self.login_frame, text="Create Account", command=self.create_account)
        self.create_button.grid(row=3, column=1, padx=5, pady=5)

        self.exit_button = tk.Button(self.login_frame, text="Exit", command=self.close)
        self.exit_button.grid(row=4, column=0, columnspan=2, padx=5, pady=5)

    def setup_chat_frame(self):
        self.chat_display = scrolledtext.ScrolledText(self.chat_frame, state="disabled", width=60, height=20)
        self.chat_display.grid(row=0, column=0, columnspan=2, padx=10, pady=10)

        # Dropdown for recipient selection
        tk.Label(self.chat_frame, text="Recipient:").grid(row=1, column=0, sticky="e", padx=5)
        self.recipient_var = tk.StringVar()
        self.recipient_var.set("All")  # default option
        self.recipient_menu = tk.OptionMenu(self.chat_frame, self.recipient_var, "All")
        self.recipient_menu.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        tk.Label(self.chat_frame, text="Message:").grid(row=2, column=0, sticky="e", padx=5)
        self.msg_entry = tk.Entry(self.chat_frame, width=40)
        self.msg_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        self.msg_entry.bind("<Return>", lambda event: self.send_chat())

        self.send_button = tk.Button(self.chat_frame, text="Send", command=self.send_chat)
        self.send_button.grid(row=3, column=1, sticky="w", padx=5, pady=5)

    def setup_command_frame(self):
        self.list_button = tk.Button(self.command_frame, text="List Accounts", command=self.list_accounts)
        self.list_button.grid(row=0, column=0, padx=5, pady=5)

        self.delete_msg_button = tk.Button(self.command_frame, text="Delete Messages", command=self.delete_messages)
        self.delete_msg_button.grid(row=0, column=1, padx=5, pady=5)

        # Dropdown for conversation viewing
        tk.Label(self.command_frame, text="View Conversation:").grid(row=1, column=0, padx=5, pady=5)
        self.view_conv_var = tk.StringVar()
        self.view_conv_var.set("Select User")
        self.view_conv_menu = tk.OptionMenu(self.command_frame, self.view_conv_var, "Select User")
        self.view_conv_menu.grid(row=1, column=1, padx=5, pady=5)

        self.view_conv_button = tk.Button(self.command_frame, text="View", command=self.view_conversation)
        self.view_conv_button.grid(row=1, column=2, padx=5, pady=5)

        self.delete_acc_button = tk.Button(self.command_frame, text="Delete Account", command=self.delete_account)
        self.delete_acc_button.grid(row=0, column=2, padx=5, pady=5)

        self.logoff_button = tk.Button(self.command_frame, text="Log Off", command=self.logoff)
        self.logoff_button.grid(row=0, column=3, padx=5, pady=5)

        self.close_button = tk.Button(self.command_frame, text="Close", command=self.close)
        self.close_button.grid(row=0, column=4, padx=5, pady=5)

        # Refresh Users button to update dropdown menus
        self.refresh_button = tk.Button(self.command_frame, text="Refresh Users", command=self.refresh_users)
        self.refresh_button.grid(row=1, column=3, padx=5, pady=5)

        self.read_button = tk.Button(self.command_frame, text="Read Unread Messages", command=self.read_messages)
        self.read_button.grid(row=1, column=4, padx=5, pady=5)


    def update_recipient_menu(self):
        # Update the recipient OptionMenu with the latest user list.
        menu = self.recipient_menu["menu"]
        menu.delete(0, "end")
        # Add "All" as an option plus all users except the current username.
        options = ["All"] + [user for user in self.user_list if user != self.username_entry.get().strip()]
        for option in options:
            menu.add_command(label=option, command=lambda value=option: self.recipient_var.set(value))
        # Set default value
        self.recipient_var.set(options[0] if options else "All")

    def update_view_conv_menu(self):
        # Update the view conversation OptionMenu with the latest user list.
        menu = self.view_conv_menu["menu"]
        menu.delete(0, "end")
        # Add a default option and all users except the current user.
        options = ["Select User"] + [user for user in self.user_list if user != self.username_entry.get().strip()]
        for option in options:
            menu.add_command(label=option, command=lambda value=option: self.view_conv_var.set(value))
        self.view_conv_var.set(options[0] if options else "Select User")

    def refresh_users(self):
        # Request a full list of users from the server.
        if self.client:
            list_msg = {"cmd": "list", "from": self.username_entry.get().strip(), "body": "*"}
            self.client.send_message(list_msg)

    def login(self):
        server_ip = self.server_ip_entry.get().strip()
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not server_ip or not username or not password:
            messagebox.showerror("Error", "Please fill in all fields.")
            return
        try:
            self.client = ChatClient(server_ip, PORT)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to server: {e}")
            return

        login_msg = {"cmd": "login", "from": username, "password": password}
        self.client.send_message(login_msg)
        threading.Thread(target=self.client.receive_loop, args=(self.handle_message,), daemon=True).start()

    def create_account(self):
        server_ip = self.server_ip_entry.get().strip()
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not server_ip or not username or not password:
            messagebox.showerror("Error", "Please fill in all fields.")
            return
        try:
            self.client = ChatClient(server_ip, PORT)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to server: {e}")
            return

        create_msg = {"cmd": "create", "from": username, "password": password}
        self.client.send_message(create_msg)
        threading.Thread(target=self.client.receive_loop, args=(self.handle_message,), daemon=True).start()

    def send_chat(self):
        message = self.msg_entry.get().strip()
        if not message:
            return
        # Use the selected recipient from the dropdown.
        recipient = self.recipient_var.get()
        chat_msg = {
            "cmd": "send",
            "from": self.username_entry.get().strip(),
            "to": recipient,
            "body": message
        }
        self.client.send_message(chat_msg)
        self.msg_entry.delete(0, tk.END)

    def list_accounts(self):
        wildcard = simpledialog.askstring("List Accounts", "Enter wildcard (leave blank for all):", parent=self.master)
        if wildcard is None:
            return
        list_msg = {"cmd": "list", "from": self.username_entry.get().strip(), "body": wildcard}
        self.client.send_message(list_msg)

    def delete_messages(self):
        indices = simpledialog.askstring("Delete Messages", "Enter message indices to delete (comma separated):", parent=self.master)
        if indices is None:
            return
        del_msg = {"cmd": "delete_msg", "from": self.username_entry.get().strip(), "body": indices}
        self.client.send_message(del_msg)

    def view_conversation(self):
        # Use the selected user from the conversation dropdown.
        other_user = self.view_conv_var.get()
        if other_user == "Select User":
            messagebox.showerror("Error", "Please select a valid user.")
            return
        view_msg = {"cmd": "view_conv", "from": self.username_entry.get().strip(), "to": other_user}
        self.client.send_message(view_msg)

    def read_messages(self):
        limit_str = simpledialog.askstring("Read Unread Messages", "Enter number of unread messages to view (0 for all):", parent=self.master)
        if limit_str is None:
            return
        try:
            limit = int(limit_str)
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid number.")
            return
        read_msg = {"cmd": "read", "from": self.username_entry.get().strip(), "body": str(limit)}
        self.client.send_message(read_msg)


    def delete_account(self):
        confirm = messagebox.askyesno("Delete Account", "Are you sure you want to delete your account? This cannot be undone.", parent=self.master)
        if confirm:
            del_msg = {"cmd": "delete", "from": self.username_entry.get().strip()}
            self.client.send_message(del_msg)

    def logoff(self):
        if self.client:
            logoff_msg = {"cmd": "logoff", "from": self.username_entry.get().strip()}
            self.client.send_message(logoff_msg)
            self.client.close()
            self.client = None
        self.chat_frame.pack_forget()
        self.command_frame.pack_forget()
        # Clear the chat display when logging off.
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.configure(state="disabled")
        self.login_frame.pack()
        # Clear username and password fields.
        self.username_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)

    def close(self):
        if self.client:
            close_msg = {"cmd": "close", "from": self.username_entry.get().strip()}
            self.client.send_message(close_msg)
            self.client.close()
            self.client = None
        self.master.destroy()

    def handle_message(self, msg):
        cmd = msg.get("cmd", "")
        body = msg.get("body", "")
        if cmd == "list":
            self.append_text("Matching accounts:\n" + body)
            # Update user list from comma-separated body.
            accounts = [x.strip() for x in body.split(",") if x.strip()]
            self.user_list = accounts
            self.update_recipient_menu()
            self.update_view_conv_menu()
        elif cmd == "login":
            if msg.get("error", False):
                messagebox.showerror("Login Failed", body)
            else:
                # Clear any existing text in the chat display.
                self.chat_display.configure(state="normal")
                self.chat_display.delete("1.0", tk.END)
                self.chat_display.configure(state="disabled")

                # Set the current username
                self.username_entry.delete(0, tk.END)
                self.username_entry.insert(0, msg.get("to", ""))
                self.login_frame.pack_forget()
                self.chat_frame.pack()
                self.command_frame.pack()
                self.append_text(body)


        elif cmd == "create":
            if msg.get("error", False):
                messagebox.showerror("Account Creation Failed", body)
            else:
                messagebox.showinfo("Account Created", body)
        elif cmd == "read":
            try:
                messages = json.loads(body)
                display_text = "Unread Messages:\n"
                for m in messages:
                    # Try to get the message id from 'id'; if not available, use 'index'
                    msg_id = m.get("id", m.get("index"))
                    display_text += f"[ID {msg_id}] {m['sender']}: {m['message']}\n"
                self.append_text(display_text)
            except Exception as e:
                self.append_text(f"Error parsing unread messages: {e}")
        elif cmd == "chat":
            try:

                messages = json.loads(body)
                if isinstance(messages, list) and messages:

                    m = messages[0]
                    sender = m.get("sender", "Unknown")
                    message_text = m.get("message", "")
                    self.append_text(f"{sender}: {message_text}")
                else:
                    # If not a list, just show the body.
                    sender = msg.get("from", "Unknown")
                    self.append_text(f"{sender}: {body}")
            except Exception as e:
                # If parsing fails, display the message as plain text.
                sender = msg.get("from", "Unknown")
                self.append_text(f"{sender}: {body}")


        elif cmd == "send":
            self.append_text(body)
        elif cmd == "delete_msg":
            self.append_text(body)
        elif cmd == "view_conv":
            self.append_text("Conversation:\n" + body)
        elif cmd == "delete":
            self.append_text(body)
            self.username_entry.delete(0, tk.END)
            self.login_frame.pack()
            self.chat_frame.pack_forget()
            self.command_frame.pack_forget()
        elif cmd == "logoff":
            self.append_text(body)
        else:
            self.append_text(f"{cmd}: {body}")

    def append_text(self, text):
        def update():
            self.chat_display.configure(state="normal")
            self.chat_display.insert(tk.END, text + "\n")
            self.chat_display.configure(state="disabled")
            self.chat_display.see(tk.END)
        self.master.after(0, update)

if __name__ == "__main__":
    root = tk.Tk()
    gui = ChatGUI(root)
    root.mainloop()
