#
#           Xiaomi Universal IR Remote Controller (Chuangmi IR) python Plugin for Domoticz
#           Version 0.2.0

#           Powered by lib python miio https://github.com/rytilahti/python-miio
#

"""
<plugin key="Chuangmi" name="Xiaomi Universal IR Remote Controller (Chuangmi IR)" author="Whilser" version="0.2.0" wikilink="https://www.domoticz.com/wiki/ChuangmiIR" externallink="https://github.com/Whilser/Xiaomi-Universal-IR-Remote-Controller-Domoticz-plugin">
    <description>
        <h2>Xiaomi Universal IR Remote Controller</h2><br/>
        <h3>Configuration</h3>
        Enter Device ID of your Chuangmi IR. If you do not know the Device ID, just leave Device ID field defaulted 0, <br/>
        this will launch discover mode for your Chuangmi devices. Go to the log, it will display the found Chuangmi devices and the Device ID you need. <br/>

    </description>
    <params>
        <param field="Mode3" label="Device ID" width="150px" required="true" default="0"/>
        <param field="Mode2" label="Debug" width="75px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal"  default="True" />
            </options>
        </param>
    </params>
</plugin>
"""

import os
import sys
import time
import os.path
import json
import binascii
import codecs
import socket

import Domoticz

module_paths = [x[0] for x in os.walk( os.path.join(os.path.dirname(__file__), '.', '.env/lib/') ) if x[0].endswith('site-packages') ]
for mp in module_paths:
    sys.path.append(mp)

from typing import Any
from miio import ChuangmiIr,DeviceException
from miio import Message

class BasePlugin:
    commandOptions =   {
        "LevelActions"  :"|||||" ,
        "LevelNames"    :"Off|Reset Level|Learn|Test|Save Level|Create" ,
        "LevelOffHidden":"true",
        "SelectorStyle" :"0"
    }

    iconName = 'ChuangmiIR'

    commandUnit = 1
    devicesCount = 1
    levelsCount = 0
    IRCodeCount = 0
    handshakeTime = 0
    discovered = False
    lastLearnedIRCode = ''

    IP = ''
    token = ''
    deviceID = 0

    data = {}
    IR_dict = {}

    def __init__(self):
        #self.var = 123
        return

    def onStart(self):
        Domoticz.Debug("onStart called")

        if Parameters['Mode2'] == 'Debug': Domoticz.Debugging(1)

        if Parameters['Mode3'] == '0':
            self.miio_discover()
            return

        self.loadConfig()
        self.CreateDevices()

        if not self.miio_discover(Parameters['Mode3']): return

        if self.iconName not in Images: Domoticz.Image('Chuangmi-icons.zip').Create()
        iconID = Images[self.iconName].ID

        if self.commandUnit not in Devices:
            Domoticz.Device(Name="Command",  Unit=self.commandUnit, TypeName="Selector Switch", Switchtype=18, Image=iconID, Options=self.commandOptions, Used=1).Create()

        DumpConfigToLog()
        Domoticz.Heartbeat(20)

    def onStop(self):
        Domoticz.Debug("onStop called")

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("onConnect called")

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called")

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

        if not self.miio_discover(Parameters['Mode3']): return

        if Unit == self.commandUnit:
            Domoticz.Debug('Handle Command Unit Commands')
            self.HandleCommandUnitCommands(Level)
            return

        Domoticz.Debug('Handle IR Commands')
        levelsList = self.data.get('Unit {0}'.format(Unit))

        if levelsList is None:
            Domoticz.Error('No config file was found for Unit {0} Remove Unit {0} from selectors.'.format(Unit))
            return

        Domoticz.Debug('Count levels: {0}'.format(len(levelsList)))

        for levels in levelsList:
            Domoticz.Debug('Record numbers {0}'.format(len(levels)))

            if Command == 'On' and levels.get('Level') == 10:
                IR_dict = dict(levels.get('LearnedCodes'))
                self.sendIRCommands(IR_dict)
                Devices[Unit].Update(nValue=1, sValue='On', TimedOut = False)

            elif Command == 'Off' and levels.get('Level') == 20:
                IR_dict = dict(levels.get('LearnedCodes'))
                self.sendIRCommands(IR_dict)
                Devices[Unit].Update(nValue=0, sValue='Off', TimedOut = False)

            elif Level == levels.get('Level'):
                IR_dict = dict(levels.get('LearnedCodes'))
                self.sendIRCommands(IR_dict)
                Devices[Unit].Update(nValue=1, sValue=str(Level), TimedOut = False)

        self.lastLearnedIRCode = ''
        self.IRCodeCount = 0
        self.IR_dict.clear()

    def HandleCommandUnitCommands(self, Level):
        if self.commandUnit not in Devices:
            Domoticz.Error('Command device is required! Restart plugin to create one.')
            return

        # Reset Level
        if Level == 10:
            self.lastLearnedIRCode = ''
            self.IRCodeCount = 0
            self.IR_dict.clear()
            Domoticz.Log('levels reset')
            Devices[self.commandUnit].Update(nValue=1, sValue=str(Level), TimedOut = False)

        # Learn Code
        if Level == 20:
           self.lastLearnedIRCode = self.learnIRCode()
           Domoticz.Debug('Learned Code: '+ str(self.lastLearnedIRCode))
           self.IRCodeCount += 1
           self.IR_dict['IRCode'+str(self.IRCodeCount)] = self.lastLearnedIRCode
           Domoticz.Log('Code Learned')
           Devices[self.commandUnit].Update(nValue=1, sValue=str(Level), TimedOut = False)

        # Test IR Commands
        if Level == 30:
            if len(self.lastLearnedIRCode) == 0:
                Domoticz.Error('No IR command received, nothing to test!')
                return

            self.sendIRCommands(self.IR_dict)
            Domoticz.Log('IR Commands sent')
            Devices[self.commandUnit].Update(nValue=1, sValue=str(Level), TimedOut = False)

        # Save command
        if Level == 40:
            if len(self.lastLearnedIRCode) == 0:
                Domoticz.Error('No IR command received, nothing to save!')
                return

            devicesCount = self.devicesCount + self.commandUnit
            self.levelsCount += 10
            if self.levelsCount == 10: self.data['Unit '+str(devicesCount)] = []
            self.data['Unit '+str(devicesCount)].append({
                'Level': self.levelsCount,
                'LearnedCodes': self.IR_dict.copy()
                })

            self.IR_dict.clear()
            self.lastLearnedIRCode = ''
            self.IRCodeCount = 0
            Domoticz.Log('levels saved')
            Devices[self.commandUnit].Update(nValue=1, sValue=str(Level), TimedOut = False)

        # Create device
        if Level == 50:
            if self.levelsCount == 0:
                Domoticz.Error('No IR Levels saved, nothing to create!')
                return

            self.devicesCount += 1

            self.dumpConfig()
            self.CreateDevices()
            self.levelsCount = 0

            Domoticz.Log('Device Created')
            Devices[self.commandUnit].Update(nValue=1, sValue=str(Level), TimedOut = False)

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called")

    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat called")

        if Parameters['Mode3'] == '0': return
        self.handshakeTime -= 1

        if self.handshakeTime <= 0:
            self.handshakeTime = 3
            if not self.miio_discover(Parameters['Mode3']): return

            try:
                m = ir.do_discover()
                Domoticz.Debug('Device ID: {0} token: {1}'.format(binascii.hexlify(ir._device_id).decode(), codecs.encode(m.checksum, 'hex').decode()))
                #Domoticz.Debug(str(ir.info()))

                for x in Devices:
                    if  Devices[x].TimedOut == True: Devices[x].Update(nValue=Devices[x].nValue, sValue=Devices[x].sValue, TimedOut = False)

            except Exception as e:
                for x in Devices:
                    if  Devices[x].TimedOut == False: Devices[x].Update(nValue=Devices[x].nValue, sValue=Devices[x].sValue, TimedOut = True)

    def dumpConfig(self):
        json_Path = os.path.join(str(Parameters['HomeFolder']), 'Chuangmi_ir'+str(Parameters["HardwareID"])+'.json')
        Domoticz.Debug('Save data to: '+json_Path)
        with open(json_Path, 'w') as outfile:
            if json.dump(self.data, outfile, indent=4, sort_keys=True): return True

    def loadConfig(self):
        json_Path = os.path.join(str(Parameters['HomeFolder']), 'Chuangmi_ir'+str(Parameters["HardwareID"])+'.json')

        if os.path.isfile(json_Path):
            Domoticz.Debug('Loading data from '+json_Path)

            with open(json_Path) as json_file:
                self.data = json.load(json_file)

        config_Path = os.path.join(str(Parameters['HomeFolder']), 'Chuangmi'+str(Parameters["HardwareID"])+'.json')

        if os.path.isfile(config_Path):
            Domoticz.Debug('Loading config from '+config_Path)

            with open(config_Path) as json_file:
                config = json.load(json_file)

            self.IP = config['IP']
            self.token = config['Token']
            self.deviceID = config['DeviceID']

    def CreateDevices(self):
        self.devicesCount = len(self.data) + self.commandUnit
        Domoticz.Debug('Total chuangmi devices: {0}'.format(self.devicesCount))

        for key in sorted(self.data):
            Domoticz.Debug('{0} was found'.format(key))

            levelsDict = self.data.get(key)
            Domoticz.Debug('Count levels: {0}'.format(len(levelsDict)))

            if int(key.strip('Unit ')) not in Devices:
                if len(levelsDict) == 1:
                    Domoticz.Device(Name=key, Unit=int(key.strip('Unit ')), Type=244, Switchtype=9, Subtype=73, Used=1).Create()
                    Domoticz.Debug('Device {0} was created.'.format(key))

                elif len(levelsDict) == 2:
                    Domoticz.Device(Name=key, Unit=int(key.strip('Unit ')), Type=244, Switchtype=0, Subtype=73, Used=1).Create()
                    Domoticz.Debug('Device {0} was created.'.format(key))

                else:
                    SelectorOptions =   {
                        "LevelActions"  :"|"*len(levelsDict),
                        "LevelNames"    :"Level|"*len(levelsDict)+"Level" ,
                        "LevelOffHidden":"true",
                        "SelectorStyle" :"0"
                    }

                    Domoticz.Device(Name=key,  Unit=int(key.strip('Unit ')), TypeName="Selector Switch", Switchtype=18, Image=12, Options=SelectorOptions, Used=1).Create()
                    Domoticz.Debug('Device {0} was created.'.format(key))

        DumpConfigToLog()

    def learnIRCode(self):
        Domoticz.Debug('Learn command called')
        if not self.miio_discover(Parameters['Mode3']): return

        learnedCode = ''
        timeout = 8

        try:
            ir.learn(key=1)
            while (len(learnedCode)==0) and (timeout > 0):
                time.sleep(1)
                timeout -= 1
                learnedCode = str(ir.read(key=1).get("code"))

        except Exception as e:
            Domoticz.Error('{0} with ID {1} is not responding, check power/network connection. Error: {2}'.format(Parameters['Name'], Parameters['Mode3'], e.__class__))

        if (len(learnedCode)==0): Domoticz.Error('No IR command received!')
        return learnedCode

    def sendIRCommands(self, IRCommands):
        if not self.miio_discover(Parameters['Mode3']): return

        try:
            for key in sorted(IRCommands):
                Domoticz.Debug('IR Code: '+key)
                Domoticz.Debug(IRCommands.get(key))
                ir.play_raw(IRCommands.get(key),frequency='')
                time.sleep(0.100)

        except Exception as e:
            Domoticz.Error('{0} with ID {1} is not responding, check power/network connection. Error: {2}'.format(Parameters['Name'], Parameters['Mode3'], e.__class__))
            self.discovered = False

            for x in Devices:
                if Devices[x].TimedOut == False: Devices[x].Update(nValue=Devices[x].nValue, sValue=Devices[x].sValue, TimedOut = True)

    def miio_discover(self, MiioID = None):
        if self.discovered: return True

        global ir

        if len(self.IP) > 0:
            try:
                Domoticz.Debug('Loaded saved configuration.')
                Domoticz.Log('Attempt to connect to Chuangmi IR device with ID: {0}, IP address: {1} and token: {2}'.format(self.deviceID, self.IP, self.token))

                ir =  ChuangmiIr(self.IP, self.token)
                info = ir.info()

                self.discovered = True
                return self.discovered

            except Exception as e:
                Domoticz.Log('Could not connect to {0} with IP {1}, starting discover.'.format(Parameters['Name'], self.IP))
                self.IP = ''

        Domoticz.Debug('Starting discover with Device ID: {}.'.format(MiioID))
        self.discovered = False
        timeout = 5
        addr = '<broadcast>'
        discoveredDevice = None
        helobytes = bytes.fromhex('21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff')

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(timeout)
        s.sendto(helobytes, (addr, 54321))

        while True:
            try:
                data, addr = s.recvfrom(1024)
                m = Message.parse(data)

                self.token = codecs.encode(m.checksum, 'hex').decode()
                self.deviceID = binascii.hexlify(m.header.value.device_id).decode()
                self.IP = addr[0]

                if ((self.token != '0'*32) and (self.token != 'f'*32)):
                    if MiioID is None:
                        item = ChuangmiIr(self.IP, self.token)
                        info = item.info()
                        Domoticz.Log('Discovered. Device Name: {0}, Device ID: {2} IP address: {1}, Token: {3}. '.format(info.model, self.IP,self.deviceID,self.token))
                    else:
                        if self.deviceID == MiioID:
                            Domoticz.Log('Connected to Chuangmi IR device ID: {0} with IP address: {1} and token: {2}'.format(self.deviceID, self.IP, self.token))

                            config = {
                                "DeviceID": self.deviceID,
                                "IP": self.IP,
                                "Token": self.token
                            }

                            config_Path = os.path.join(str(Parameters['HomeFolder']), 'Chuangmi'+str(Parameters["HardwareID"])+'.json')
                            with open(config_Path, 'w') as outfile:
                                if json.dump(config, outfile, indent=4): Domoticz.Debug('Config file was saved.')

                            self.discovered = True
                            self.handshakeTime = 3
                            ir =  ChuangmiIr(self.IP, self.token)

                            for x in Devices:
                                if  Devices[x].TimedOut == True: Devices[x].Update(nValue=Devices[x].nValue, sValue=Devices[x].sValue, TimedOut = False)

                            return self.discovered

            except socket.timeout:
                Domoticz.Debug('Discovery done')
                if ((MiioID is not None) and (self.discovered == False)):
                    Domoticz.Error('Could not discover Chuangmi IR with Device ID = {0}. Check power/network/Device ID.'.format(MiioID))
                    self.IP = ''
                    self.handshakeTime = 3
                    for x in Devices:
                        if  Devices[x].TimedOut == False: Devices[x].Update(nValue=Devices[x].nValue, sValue=Devices[x].sValue, TimedOut = True)

                return self.discovered
            except Exception as ex:
                Domoticz.Error('Error while reading discover results: {0}'.format(ex))
                break

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

    # Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
        Domoticz.Debug("Device TimedOut: " + str(Devices[x].TimedOut))
    return
