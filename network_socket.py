import socket

class NetworkSocket():

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False

    def connect_socket(self, ip, port, password):
        print "connecting..."
        ### Try to connect
        self.connected = 0
        try:
            self.sock.connect((ip, port))
        except Exception, e:
            print e
            self.sock.close()
            return 0

        ### check for correct module
        self.write("\x10")
        d = []
        d= self.read(3)
        if d[0] != '\x12':
            print "Wrong module type found"
            self.sock.close()
            return 0


        ### Check to see if password is enabled
        self.write("\x7a")
        d = []
        d = self.read(1)
        if d[0] == '\x00':                          ### Password is enabled
            passwordString = '\x79' + password      ### Put together password command and send it
            self.write(passwordString)
            d = self.read(1)
            if d[0] != '\x01':                      ### The password was wrong
                print "Wrong password"
                self.sock.close()
                return 0
        return 1


    def write(self, mesg):
        try:
            self.sock.sendall(mesg)
        except Exception, e:
            print "Error writing message"

    def read(self, readnum):
        chunks = []
        bytes_recd = 0
        while bytes_recd < readnum:
            chunk = self.sock.recv(min(readnum - bytes_recd, 2048))
            if chunk == '':
                print "Error reading message"
                raise RuntimeError("socket connection broken")
            chunks.append(chunk)
            bytes_recd = bytes_recd + len(chunk)
        return ''.join(chunks)

    def close_socket(self):
        try:
            self.sock.close()
        except Exception, e:
            print e
        print "Disconnected"
