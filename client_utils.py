from socket import *
import struct
from io import TextIOWrapper
from crcmod import mkCrcFun
from hashlib import sha1
from sys import getsizeof

MAX_PACKET_SIZE = 1024
PACKET_HEADER_SIZE = 16 + 16 + 16 + 16 + 16 # source port + destination port + length + number of packet
BUFFER_SIZE = MAX_PACKET_SIZE - PACKET_HEADER_SIZE

# Create 16bit CRC function
crc16 = mkCrcFun(0x18005, rev=False, initCrc=0xFFFF, xorOut=0x0000)

def send_file_selrep(f: TextIOWrapper, source: tuple[str, int], target: tuple[str, int], window_size: int) -> bool:
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.settimeout(1.0)
    encoded_file = sha1(f.read()).hexdigest()
    f.close()

    sent_packets = {}
    stuff_to_send = True
    

    curr_packet_num = 1

    # Break on end of file
    while stuff_to_send:

        # Sending packets up to the size of sending window
        while stuff_to_send and len(sent_packets) < window_size:
            if BUFFER_SIZE < len(encoded_file):
                data = encoded_file[:BUFFER_SIZE]
            else:
                data = encoded_file
                stuff_to_send = False
            crc = crc16((str(source[1]) + str(target[1]) + str(BUFFER_SIZE) + data).encode())

            # Creating packet using struct, H is unsigned short (16bit)
            packet = struct.pack(f"!HHHHH{BUFFER_SIZE}s", source[1], target[1], BUFFER_SIZE, crc, curr_packet_num, data.encode())
            if sock.sendto(packet, target):
                sent_packets[curr_packet_num] = packet
                encoded_file = encoded_file[BUFFER_SIZE:]
                print(f"Sent packet number {curr_packet_num}.")
            else:
                print(f"Failed to send packet {curr_packet_num}")

        print("Sending window full, awaiting ACK ...")
        stuff_to_receive = True

        # Will wait for ACKs and handle lost packets
        while stuff_to_receive:
            ack = sock.recv(8).decode()
            if len(ack) > 0:
                next_packet = int(ack)

                # If ACK asks for previously unsent packet, all previous were successfully delivered
                # Clear packet history and break ACK loop
                if next_packet > max(sent_packets.keys()):
                    print(f"Target requests next packet {next_packet}, clearing window")
                    sent_packets = dict()
                    break
                else:

                    # Packet got lost, resending
                    print(f"Target requests resend of packet {next_packet}.")
                    if sock.sendto(packet, target):
                        print(f"Resent packet number {next_packet}.")
                    else:
                        print(f"Failed to resend packet {next_packet}.")

            else:
                # ack is an empty string
                stuff_to_receive = False

        print("Nothing else to receive, continue sending")


def receive_file_selrep(f_path: str, receiver_port: int, window_size: int) -> None:
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.bind(("0.0.0.0", receiver_port))

    in_window = 0
    received_packets = {}
    stuff_to_receive = True
    client_address = None
    
    print(f"Successfully opened file {f_path}.")
    while stuff_to_receive:
        while stuff_to_receive and in_window < window_size:
            packet, client_address = sock.recvfrom(MAX_PACKET_SIZE)
            data_size = getsizeof(packet) - PACKET_HEADER_SIZE
            source, target, length, crc, sequence_number, data = struct.unpack(f"!HHHHH{data_size}s", packet)

        
            crc_ok = crc == crc16((str(source) + str(target) + str(length) + data).encode())

            if crc_ok and sequence_number not in received_packets.keys():
                print(f"Packet number {sequence_number} accepted.")
                received_packets[sequence_number] = data
                in_window += 1
                
                # Not the entire allowed buffer was used - presumably EOF
                if length < BUFFER_SIZE:
                    stuff_to_receive = False
            else:
                print(f"CRC check failed on packet number {sequence_number}.")

        next_expected = max(received_packets.keys()) + 1
        all_the_packets_we_want = list(range(1, next_expected + 1))

        # Filter out packets that we have received successfully, use set to get rid of duplicates
        missing_packets = set(filter(lambda i: i in received_packets.keys(),all_the_packets_we_want))

        while missing_packets:
            sequence_number = missing_packets.pop()
            ack_packet = struct.pack("!H", sequence_number)
            if sock.sendto(ack_packet, client_address):
                print(f"Sent ACK with request for {'missing' if sequence_number < next_expected else 'next'} packet number {sequence_number}.")
            else:
                print(f"Failed to send ACK with request for {'missing' if sequence_number < next_expected else 'next'} packet number {sequence_number}.")