import serial
import struct
import time
import threading

ser = serial.Serial('/dev/ttyUSB0')
time.sleep(2)

START =  b'\x61'
END =    b'\x62'
ESC =    b'\x63'
TSTART = b'\x64'
TEND =   b'\x65'
TESC =   b'\x66'
MESSAGE_LENGTH = 20
ACK_TIMEOUT = 5000



class FullSerial():
    def __init__(self, device, baudrate=9600):
        self.serial = serial.Serial(device, timeout=1, baudrate=baudrate)
        self.receptionstarted = False
        self.receptiondata = bytearray()
        self.esc = False
        self.id = set(range(0,20))
        self.__idlock = threading.Lock()
        self.__seriallock = threading.Lock()
        

        # The listenner
        """thread = threading.Thread(target=self.listenner, args=())
        thread.daemon = True                            # Daemonize thread
        thread.start()                                  # Start the execution
        """

    def getMessage(self, expected_id):
        i = 0
        """while True:
            byte = self.serial.read(1)
            print(byte)
        """
        messagereceived = False
        start_time = self.__getMillis()
        while (self.__getMillis() - start_time) < ACK_TIMEOUT:
            byte = self.serial.read(1)
            #print(byte)
            if not byte:
                #print("Nothing received")
                continue
            if byte == START:
                #print("START")
                self.receptionstarted = True
                self.receptiondata = bytearray()
                continue
            else:
                if self.receptionstarted :
                    if byte == END:
                        #print("END")
                        self.receptionstarted = False
                        #print("Data received :")
                        #print(self.receptiondata)
                        
                        action = self.receptiondata[1]
                        message_id = self.receptiondata[2]
                        if expected_id != message_id:                      # Check if the message is expected
                            continue
                        data = None
                        if len(self.receptiondata) > 3:
                            data = self.receptiondata[3:]  
                        return action, message_id, data
            
                    if byte == ESC:
                        self.esc = True
                        continue
                    else:
                        if self.esc:
                            if byte == TSTART:
                                self.receptiondata += START
                            elif byte == TEND:
                                self.receptiondata += END
                            elif byte == TESC:
                                self.receptiondata += ESC
                            else:
                                raise ValueError("Unknow escaped character : %s" % byte)
                            self.esc = False
                        else:
                            self.receptiondata += byte
                    continue
        raise TimeoutError("Ack timeout expired...")

                

    def __get_id(self):
        with self.__idlock:
            if len(self.id) == 0:
                raise RuntimeError("No more message ids available")
            return self.id.pop()
        

    def __release_id(self, message_id):
        self.id.add(message_id)


    def __getMillis(self):
        return int(round(time.time() * 1000))            
            
        
    def sendmessage(self, action, values, ack=False, immediate=False):
        self.action = action
        self.values = values
        self.ack = ack
        self.immediate = immediate

        self.payload = bytearray()                                   # Prepare the payload
        if ack:
            sent_id = self.__get_id()
            self.payload = self.payload + bytes((sent_id, ))
        else:
            self.payload = self.payload + bytes((0, ))

        
        self.payload = self.payload + bytes([action])
        
        for value in self.values:
            if isinstance(value, int):
                if not(-32768 <= value <= 32767):
                    raise ValueError('Arduino integer must be in range(-32,768, 32,767)')
                lowbyte, highbyte = struct.pack('h', value)
                self.payload = self.payload + bytes([highbyte])           # First byte
                self.payload = self.payload + bytes([lowbyte])            # Second byte
            if isinstance(value, str):
                self.payload = self.payload + bytearray(value, "utf-8")
                self.payload = self.payload + bytearray([0])
        #print(self.payload)
        self.__seriallock.acquire()
        self.serial.write(START)                                   # The START flag
        self.__writetoserial(self.__checksum(self.payload))        # The checksum
        self.__writetoserial(self.payload)                         # The payload
        self.serial.write(END)                                     # The END flag
        
        if ack:
            action, message_id, data = self.getMessage(sent_id)
            self.__release_id(message_id)
            self.__seriallock.release()
            return data
        self.__seriallock.release()

    def __writetoserial(self, data):
        data = data.replace(ESC, ESC + TESC)
        data = data.replace(START, ESC + TSTART)
        data = data.replace(END, ESC + TEND)
        self.serial.write(data)

    def __checksum(self, data):
        checksum = 0
        for c in data:
            checksum = checksum ^ c
        return bytes((checksum, ))

    def parsedata(self, dataformat, data):
        values = []
        index = 0
        for f in dataformat:
            if f == 'i':
                if len(data) < (index + 2):
                    raise IndexError("Too much values excepted (%s) for %s" % (dataformat, data))
                value = (data[index]<<8)+data[index+1]
                index += 2
                values.append(value)
            elif f == 's':
                i = 0
                mystring = ""
                while True:
                    byte = data[index]
                    index += 1
                    if byte == 0:
                        break
                    elif index > len(data):
                        raise IndexError("Too much values excepted (%s) for %s" % (dataformat, data))
                    mystring += chr(byte)
                values.append(mystring)                    
        return values
                



ard = FullSerial('/dev/ttyUSB0', baudrate=9600)

for i in range(0, 40000):
    #print(i)
    resp = ard.sendmessage(2, (8,i), ack=True)
    #print(resp)
    values = ard.parsedata('ii', resp)
    print(values)
    time.sleep(2)

