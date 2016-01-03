import serial
import struct
import sys
import time
import threading
import traceback


START =  b'\x61'
END =    b'\x62'
ESC =    b'\x63'
TSTART = b'\x64'
TEND =   b'\x65'
TESC =   b'\x66'
MESSAGE_LENGTH = 20
ACK_TIMEOUT = 6000



class FullSerial():
    def __init__(self, device, baudrate=9600):
        self.serial = serial.Serial(device, timeout=1, baudrate=baudrate)
        time.sleep(2)
        self.serial.flushInput()
        self.receptionstarted = False
        self.receptiondata = bytearray()
        self.esc = False
        self.id = set(range(1,20))
        self.__idlock = threading.Lock()
        self.__seriallock = threading.Lock()
        self.__actions = {}
        self.__stoprequested = False
        self.__threadstarted = False
        self.__ackwaited = {}
        self.__ackdata = {}
        

    def begin(self):
        self.__threadstarted = True
        self.serial.timeout = 0.1
        self.thread = threading.Thread(target=self.listenner, args=())
        self.thread.daemon = True                            # Daemonize thread
        self.thread.start()                                  # Start the execution


    def end(self):
        print("A")
        self.__stoprequested = True
        self.thread.join()
        print("B")


    def listenner(self):
        while not self.__stoprequested:
            msg = self.__read()
            if msg == None:
                print(self.__ackwaited)
                print(self.__ackdata)            
                continue
            action, messageid, data = msg
            #print("msg received : ");
            #print(msg)

            if action == 0:                        # ACK received
                if messageid in self.__ackwaited:
                    self.__ackdata[messageid] = data
                    self.__ackwaited[messageid].set()
                    continue
                else:
                    print("ack inconnu")
            if action in self.__actions:
                self.__actions[action](messageid, data)
            
        print("Stopping listener")
        self.__threadstarted = False
        
        
    def __read(self, timeout=None, expectedid = None):
        messagereceived = False
        start_time = self.__getMillis()
        while True:
            if timeout:
                if ((self.__getMillis() - start_time) > timeout):
                    print("to")
                    return None
            if self.__stoprequested:
                return None

            byte = self.serial.read(1)
            #print(byte)
            if byte == START:
                #print("START")
                self.receptionstarted = True
                self.receptiondata = bytearray()
            elif self.receptionstarted :
                if byte == END:
                    #print("END")
                    self.receptionstarted = False
                    #print("Data received :")
                    #print(self.receptiondata)
                    message_id = self.receptiondata[2]
                    if (expectedid == None) or (expectedid == message_id):
                        action = self.receptiondata[1]
                        data = None
                        if len(self.receptiondata) > 3:
                            data = self.receptiondata[3:]
                        return action, message_id, data
                    print("unexpected msg: %s" % self.receptiondata)
                                                    
        
                elif byte == ESC:
                    self.esc = True
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
    

    def getAck(self, expected_id):
        i = 0
        """while True:
            byte = self.serial.read(1)
            print(byte)
        """
        result = self.__read(ACK_TIMEOUT, expected_id)
        if result == None:
            raise TimeoutError("Ack timeout expired...")

        return result
                

    def __get_id(self):
        with self.__idlock:
            if len(self.id) == 0:
                raise RuntimeError("No more message ids available")
            return self.id.pop()
        

    def __release_id(self, message_id):
        self.id.add(message_id)


    def __getMillis(self):
        return int(round(time.time() * 1000))


    def __sendmessage(self, action, messageid, values):
        payload = bytearray()
        payload = bytes((messageid, ))
        payload = payload + bytes([action])

        if values:
            for value in values:
                if isinstance(value, int):
                    if not(-32768 <= value <= 32767):
                        raise ValueError('Arduino integer must be in range(-32,768, 32,767)')
                    lowbyte, highbyte = struct.pack('h', value)
                    payload = payload + bytes([highbyte])           # First byte
                    payload = payload + bytes([lowbyte])            # Second byte
                if isinstance(value, str):
                    payload = payload + bytearray(value, "utf-8")
                    payload = payload + bytearray([0])
                    
        #print(self.payload)
        #print("lock acquired for :")
        #print(action, messageid, values)
        self.__seriallock.acquire()
        self.serial.write(START)                                   # The START flag
        #print(START, end="")
        self.__writetoserial(self.__checksum(payload))        # The checksum
        self.__writetoserial(payload)                         # The payload
        
        self.serial.write(END)                                     # The END flag
        #print(END)
        
            
        
    def sendmessage(self, action, values=None, ack=False):
        
        self.action = action
        self.ack = ack
                                           # Prepare the payload
        if ack:
            messageid = self.__get_id()
        else:
            messageid = 0

        if ack and self.__threadstarted:    # thread mode, need a lock
            evt = threading.Event()            
            self.__ackwaited[messageid] = evt

        self.__sendmessage(action, messageid, values)       
        
        
        if ack:
            if self.__threadstarted:                                                #Mode thread
                self.__seriallock.release()
                #print("lock released for :")
                #print(action, messageid, values)
                result =  evt.wait(ACK_TIMEOUT / 1000)
                del self.__ackwaited[messageid]
                del evt
                
                self.__release_id(messageid)
                if not result:
                    print("id:{:02x} , action:{:02x}, {}".format(messageid, action, values));
                    0/0
                    raise TimeoutError("Ack timeout expired...")
                data = self.__ackdata[messageid]
                del self.__ackdata[messageid]
                
                return data
            else:                                                                   #Mode sans thread
                action, messageid, data = self.getAck(messageid)
                self.__release_id(messageid)
                self.__seriallock.release()
                return data
        self.__seriallock.release()
        

    def sendack(self, messageid, data=None):
        self.__sendmessage(0, messageid, data)
        self.__seriallock.release()
        

    def __writetoserial(self, data):
        data = data.replace(ESC, ESC + TESC)
        data = data.replace(START, ESC + TSTART)
        data = data.replace(END, ESC + TEND)
        self.serial.write(data)
        #print(' '.join('{:02x}'.format(x) for x in data), end="")

    def __checksum(self, data):
        checksum = 0
        for c in data:
            checksum = checksum ^ c
        return bytes((checksum, ))

    def parsedata(self, dataformat = None, data = None):
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
                
    def attach(self, action, function):
        self.__actions[action] = function


pccnt = 0

#Ajouter le messageid avec un decorateur ?
def test(messageid, data):
    global pccnt
    ard.sendack(messageid, (pccnt, ))
    print("envoi de la valeur a l'ard: %s" % pccnt)
    pccnt = pccnt + 1
    if pccnt == 32767:
        pccnt = 0
    

ard = FullSerial('/dev/ttyUSB0', baudrate=115200)

ard.attach(2, test)

#ard.begin()
"""
while True:-
    try:
        time.sleep(0.1)
    except (KeyboardInterrupt, SystemExit):
        ard.end()
        sys.exit(0)
"""
"""
resp = ard.sendmessage(2, (i, "i from ard ?"), ack=True)
values = ard.parsedata("is", resp)
print(values)"""

n = time.time()
error = 0
for i in range(0, 2000000):
    #print(i)
    try:
        resp = ard.sendmessage(2, (0,), ack=True)
        #resp = ard.sendmessage(2, (i,) , ack = True)
        values = ard.parsedata("i", resp)
        #print("<- %s" % values[0])
        #print(values)
        #time.sleep(10)
    except:
        pass
       
        error= error + 1
        #print("--")
        print(i, time.time() - n, "%s/%s" %(error, i))
        #print(''.join('{:02x}'.format(x) for x in ard.payload))
        
        #print("--")
        0/0
        """
        print(sys.exc_info()[0])
        print(sys.exc_info()[1])
        print(dir(sys.exc_info()[2]))
        traceback.print_exc(file=sys.stdout)
        """

    if i%1000 == 0:
        print(i, error, values, pccnt)

#time.sleep(10)
ard.end()
