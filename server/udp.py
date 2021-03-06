import os
import os.path
import socket
import sys
import threading
import time
from datetime import datetime

from commands import client_commands, server_commands, help_list

PORT = 5000
IP = '127.0.0.1'

BUFFER_SIZE = 1024
WINDOW_SIZE = 4096

TIMEOUT = 20

OK_STATUS = 200
SERVER_ERROR = 500


def is_file_exist(file_name):
    return os.path.exists(file_name)


def echo(addr, body):
    time.sleep(0.001)
    send_data(addr, body)


def send_time(addr):
    server_time = "Server time: " + str(datetime.now())[:19]
    send_data(addr, server_time)


def exit_client(addr):
    clients_addr.remove(addr)


def save_to_waiting_clients(addr, command, file_name, progress):
    waiting_clients.append(
        {
            'addr': addr[0],
            'command': command,
            'file_name': file_name,
            'progress': progress
        })


def search_by_addr(list, addr):
    found_client = [element for element in list if element['addr'] == addr[0]]
    return found_client[0] if len(found_client) > 0 else False


def handle_disconnect(client, command, file_name, progress):
    save_to_waiting_clients(addr, command, file_name, progress)
    time.sleep(1)
    print("lost connection")


def download(addr, file_name):
    global WINDOW_SIZE

    f = open(file_name, "rb+")

    size = int(os.path.getsize(file_name))

    print("File size: %f" % (size / (1024 * 1024)))

    client_window = int(get_data()[0])

    if (WINDOW_SIZE > client_window):
        WINDOW_SIZE = client_window

    send_data(addr, WINDOW_SIZE)

    send_data(addr, size)

    data_size_recv = int(get_data()[0])

    waiting_client = search_by_addr(waiting_clients, addr)
    if (len(waiting_clients) > 0 and waiting_client != False and waiting_client["file_name"] == file_name and
            waiting_client['command'] == 'download'):
        waiting_clients.remove(waiting_client)
        data_size_recv = int(waiting_client['progress'])

    send_data(addr, data_size_recv)

    f.seek(data_size_recv, 0)

    current_pos = data_size_recv

    time_start = datetime.now()

    speeds = []
    time_package_start = datetime.now()

    while (1):
        try:
            if (current_pos >= size):
                server_udp.sendto(b"EOF", addr)
                break
            else:
                data_file = f.read(BUFFER_SIZE)
                server_udp.sendto(data_file, addr)
                current_pos = current_pos + BUFFER_SIZE
                f.seek(current_pos)

            client_window = client_window - BUFFER_SIZE
            if (client_window == 0):
                time_package_end = datetime.now()

                delta_time_package = (time_package_end - time_package_start).microseconds / 1000000

                speed = BUFFER_SIZE / (delta_time_package * 1024 * 1024)
                speeds.append(speed)  # megabyte / s

                received_data = get_data()[0]
                client_window = WINDOW_SIZE

                if (received_data == "ERROR"):
                    handle_disconnect(addr, "download", file_name, data_size_recv)
                    break
                else:
                    data_size_recv = int(received_data)

                time_package_start = datetime.now()

        except KeyboardInterrupt:
            f.close()
            server_udp.close()
            os._exit(1)

    time_end = datetime.now()

    delta_time = (time_end - time_start).microseconds / 1000

    print("Total time: %f ms" % delta_time)

    average_speed = float(sum(speeds)) / max(len(speeds), 1)
    average_speed = average_speed * (WINDOW_SIZE / BUFFER_SIZE)

    print("Average speed: %f m/s" % average_speed)

    f.close()


def upload(addr, file_name):
    global WINDOW_SIZE

    client_window = int(get_data()[0])  # 1

    if (WINDOW_SIZE > client_window):
        WINDOW_SIZE = client_window

    send_data(addr, WINDOW_SIZE)  # 2

    size = int(get_data()[0])  # 3

    data_size_recv = get_data()[0]  # 4

    if (data_size_recv):
        data_size_recv = int(data_size_recv)

    waiting_client = search_by_addr(waiting_clients, addr)
    if (len(waiting_clients) > 0 and waiting_client != False and waiting_client["file_name"] == file_name and
            waiting_client['command'] == 'upload'):
        waiting_clients.remove(waiting_client)
        data_size_recv = int(waiting_client['progress'])

    send_data(addr, data_size_recv)  # 5

    if (data_size_recv == 0):
        f = open(file_name, "wb")
    else:
        f = open(file_name, "rb+")

    current_pos = data_size_recv

    f.seek(current_pos, 0)

    time_start = datetime.now()

    speeds = []
    time_package_start = datetime.now()

    while (1):
        try:
            data = server_udp.recvfrom(BUFFER_SIZE)[0]

            if data:
                if data == b"ERROR":
                    handle_disconnect(addr, "upload", file_name, data_size_recv)
                    break

                if data == b"EOF":
                    break
                else:
                    f.seek(current_pos, 0)
                    f.write(data)
                    current_pos += len(data)
                    client_window = client_window - len(data)
                    if (client_window == 0):
                        client_window = WINDOW_SIZE

                        time_package_end = datetime.now()

                        delta_time_package = (time_package_end - time_package_start).microseconds / 1000000
                        time_package_start = datetime.now()

                        speed = BUFFER_SIZE / (delta_time_package * 1024 * 1024)
                        speeds.append(speed)  # megabyte / s

                        received_data = get_data()[0]

                        if (received_data == "ERROR"):
                            handle_disconnect(addr, "upload", file_name, data_size_recv)
                            break
                        else:
                            data_size_recv = int(received_data)

        except KeyboardInterrupt:
            f.close()
            server_udp.close()
            os._exit(1)

    time_end = datetime.now()

    delta_time = (time_end - time_start).microseconds / 1000

    print("Total time: %f ms" % delta_time)

    average_speed = float(sum(speeds)) / max(len(speeds), 1)
    average_speed = average_speed * (WINDOW_SIZE / BUFFER_SIZE)

    print("Average speed: %f m/s" % average_speed)

    f.close()


def add_client_address(addr):
    if not addr in clients_addr:
        clients_addr.append(addr)


def get_data():
    data, address = server_udp.recvfrom(BUFFER_SIZE)
    data = data.decode('utf-8')
    return [data, address]


def send_data(addr, data):
    server_udp.sendto(str(data).encode('utf-8'), addr)


def send_status_and_message(addr, request, status, message):
    message = str("" + request + " " + str(status) + " " + message)
    send_data(addr, message)


def send_status(addr, request, status):
    message = str("" + request + " " + str(status))
    send_data(addr, message)


def handle_client_request(addr, request):
    global body
    body = "Body is empty"
    command = request.split()
    name_command = command[0]

    if len(command) == 2:
        body = command[1]

    if client_commands.get(name_command) == "download":
        if is_file_exist(body):
            send_status(addr, name_command, OK_STATUS)
            download(addr, body)
        else:
            no_file = "File: " + body + " is not exist."
            send_status_and_message(addr, name_command, SERVER_ERROR, "No such file")

    elif client_commands.get(name_command) == "upload":
        send_status(addr, name_command, OK_STATUS)
        upload(addr, body)

    elif client_commands.get(name_command) == "echo":
        send_status(addr, name_command, OK_STATUS)
        echo(addr, body)

    elif client_commands.get(name_command) == "time":
        send_status(addr, name_command, OK_STATUS)
        send_time(addr)

    elif client_commands.get(name_command) == "exit":
        send_status(addr, name_command, OK_STATUS)
        exit_client(addr)

    else:
        send_status_and_message(addr, name_command, SERVER_ERROR, "Unknown command")


def show_start_message():
    show_server_menu()


def server_cli():
    while True:
        command = input()
        parsed_data = parse_server_command(command)
        if not parsed_data:
            pass
        elif len(parsed_data) == 2:
            command, body = parsed_data
            handle_server_command(command, body, server_udp)


def parse_server_command(command):
    command = command.split()
    if len(command) == 0:
        return False

    name_command = command[0]
    if len(command) == 2:
        body = command[1]
    else:
        body = ""
    return [name_command, body]


def handle_server_command(command, body, server):
    if server_commands.get(command) == "help":
        show_server_menu()
    if server_commands.get(command) == "echo":
        print(body)
    if server_commands.get(command) == "time":
        print("Server time: " + str(datetime.now())[:19])
    if server_commands.get(command) == "exit":
        server.close()
        os._exit(1)


def show_server_menu():
    for x in help_list:
        print(x, ": ", help_list[x])


server_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server_address = (IP, PORT)
server_udp.bind(server_address)

show_start_message()

clients_addr = []
waiting_clients = []

while True:
    request, addr = get_data()

    add_client_address(addr)

    handle_client_request(addr, request)
