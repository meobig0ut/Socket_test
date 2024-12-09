import socket
import os
import threading
from tkinter import filedialog

# Tạo UDP socket
host = "127.0.0.1"
port = 65000
buffer = 1024
serverAddress = (host, port)
Format = "utf8"
client_address = None
socket_lock = threading.Lock()

def read_file(file_name):
    sending = ""
    try:
        with open(file_name, "r") as f:
            for line in f:
                if line.strip():
                    sending += line.strip() + '\n'
    except FileNotFoundError:
        print(f"File not found: {file_name}")
    return sending


#Gửi dữ liệu tên file đến client
def send_files_name(files_name, socket_object):
    global client_address
    list_files_name = read_file(files_name)
    data, curr_client_address = socket_object.recvfrom(buffer)
    
    #Khi chưa kết nối với bất kỳ client nào 
    if client_address is None:
        client_address = curr_client_address
        print(f"Chap nhan client voi dia chi: {client_address} \n")
    
    #Kiểm tra xem có phải client đang kết nối hay không
    if client_address == curr_client_address:
        socket_object.sendto(list_files_name.encode(Format), client_address)
    else:
        print("Khong nhan client moi\n")


#nhan ten cac file can tai tu client
#conn chinh la server
def recvFileList(conn):
    first = True
    try:
        while True:
            filename, curr_client_address = conn.recvfrom(buffer) # Sử dụng mã hóa UTF-8
            if (curr_client_address != client_address):
                print("Da co client ket noi, khong nhan client moi\n")
                continue
            if not filename:
                break
            print(f"Yêu cầu tải file: {filename}")
            # Kiểm tra xem file có tồn tại trên server không
            if not os.path.exists(filename):
                print(f"File '{filename}' không tồn tại trên server.")
                conn.sendto("NOT_FOUND".encode(Format), client_address)
            else:
                conn.sendto("OK".encode(Format), client_address)
                handle_download(conn, filename)
        
    except Exception as e:
        print(f"Lỗi kết nối với client: {e}")
    finally:
        conn.close()

def handle_download(conn, file_name):
    """Xử lý yêu cầu tải xuống file."""
    response, curr_client_address = conn.recvfrom(buffer)
    print(response)
    if response == "CANCEL":
        print(f"Client hủy tải file '{file_name}'.")
        return
    elif response != "OK":
        print("Client không chọn folder để tải.")
        return
    else:
        chunks = []
        try:
            chunks = split_file_into_4_chunks(file_name)
            for chunk in chunks:
                print(os.path.getsize(chunk), "byte")
           
            threads = []
            for index, chunk_path in enumerate(chunks):
                thread = threading.Thread(target=send_chunk, args=(conn, index, chunk_path))
                threads.append(thread)
                thread.start()
           
            for thread in threads:
                thread.join()

            print(f"File '{file_name}' đã được gửi thành công.")
        except Exception as e:
            print(f"Lỗi khi xử lý tải xuống: {e}")
        finally:
            for chunk in chunks:
                if os.path.exists(chunk):
                    os.remove(chunk)

            os.removedirs("chunks")

def split_file_into_4_chunks(file_name):
    """Chia file thành 4 chunk."""
    chunks = []
    try:
        with open(file_name, "rb") as f:
            data = f.read()
            chunk_size = len(data) // 4
            output_dir = "chunks"
            os.makedirs(output_dir, exist_ok=True)  # Đảm bảo thư mục tồn tại
            for i in range(4):
                start = i * chunk_size
                end = start + chunk_size if i < 3 else len(data)  # Phần còn lại vào chunk cuối
                chunk_data = data[start:end]
                chunk_path = os.path.join(output_dir, f"chunk_{i}.tmp")
                with open(chunk_path, "wb") as chunk_file:
                    chunk_file.write(chunk_data)
                chunks.append(chunk_path)

        return chunks
    except FileNotFoundError:
        print(f"File '{file_name}' không tồn tại.")
        return None
    except Exception as e:
        print(f"Lỗi khi chia file: {e}")
        return None

def send_chunk(conn, chunk_index, chunk_path):
    """Gửi chunk đến client."""
    try:
        with socket_lock:
            chunk_size = os.path.getsize(chunk_path)
            # Gửi metadata chunk
            conn.sendto(f"{chunk_index}:{chunk_size}\n".encode(Format), client_address)
            print(f"Đang gửi metadata cho chunk_{chunk_index} (kích thước: {chunk_size}).")
            ack_tmp = ""
            while True:
                ack_tmp, curr_client_address = conn.recvfrom(buffer)
                if curr_client_address != client_address:
                    print("Da co client ket noi, khong nhan client moi\n")
                else:
                    break
            ack = ack_tmp.decode(Format)
            if ack != 'ACK_META':
                raise Exception("Không nhận được xác nhận metadata.")

            # Gửi dữ liệu chunk
            conn.sendto("DATA_START".encode(Format), client_address)
            with open(chunk_path, 'rb') as chunk_file:
                while True:
                    data = chunk_file.read(1024)
                    if not data:
                        break
                    conn.sendto(data, client_address)
            conn.sendto("DATA_END".encode(Format), client_address)
           
            # Chờ xác nhận cuối
            while True: 
                ack, curr_client_address = conn.recvfrom(buffer)
                if (curr_client_address == client_address):
                    break
            
            ack = ack.decode(Format).strip()
            if ack != 'COMPLETE':
                raise Exception("Không nhận được xác nhận hoàn tất từ client.")
            print(f"Đã gửi xong chunk_{chunk_index} (kích thước: {chunk_size}).")
    except Exception as e:
        print(f"Lỗi khi gửi chunk {chunk_index}: {e}")


def main():
    try:
        socket_object = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        socket_object.bind(serverAddress)
        print("Server is running and waiting for clients...")
        files_name = "files.txt"
        
        while True:
            # Wait for a client request
            try:
                send_files_name(files_name, socket_object)
                print("Dia chi: ", client_address, "\n")
                recvFileList(socket_object)        
            except Exception as e:
                    print(f"Error during client communication: {e}")
    except Exception as e:
        print(f"Server error: {e}")
    finally:
        print("Shutting down server.") 
        socket_object.close()

if __name__ == "__main__":
    main()   
