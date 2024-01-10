import argparse
from client_utils import receive_file_selrep

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Receiver client",
        description="Receives file using UDP with Selective-Repeat and saves it to given path"
    )
    parser.add_argument("path", type=str,  help="where to save received file")
    parser.add_argument("port", type=int,  help="which port to use to receive file")
    parser.add_argument("sender_address", type=str, default="127.0.0.1", help="specify target address")
    parser.add_argument("sender_port", type=int, default=1401, help="specify target port")
    parser.add_argument("-window", dest="window", type=int, required=False, default=10, help="received packets limit before sending ACKs")
    args = parser.parse_args()
    sender = (args.sender_address, args.sender_port)
    print(args)
    receive_file_selrep(args.path, args.port, sender, args.window)
