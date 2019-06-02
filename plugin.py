#
#           Xiaomi Universal IR Remote Controller (Chuangmi IR) python Plugin for Domoticz
#           Version 0.1.0

#           Powered by lib python miio https://github.com/rytilahti/python-miio
#

"""
<plugin key="Chuangmi" name="Xiaomi Universal IR Remote Controller (Chuangmi IR)" author="Whilser" version="0.1.0" wikilink="https://www.domoticz.com/wiki/ChuangmiIR" externallink="https://github.com/Whilser/Xiaomi-Universal-IR-Remote-Controller-Domoticz-plugin">
    <params>
        <param field="Address" label="IP Address" width="200px" required="true" default="127.0.0.1"/>
        <param field="Mode1" label="Token" width="300px" required="true" default="000000000000"/>
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

import Domoticz

module_paths = [x[0] for x in os.walk( os.path.join(os.path.dirname(__file__), '.', '.env/lib/') ) if x[0].endswith('site-packages') ]
for mp in module_paths:
    sys.path.append(mp)

from typing import Any
from miio import ChuangmiIr,DeviceException

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
    lastLearnedIRCode = ''

    data = {}
    IR_dict = {}

    def __init__(self):
        #self.var = 123
        return

    def onStart(self):
        if Parameters['Mode2'] == 'Debug':
            Domoticz.Debugging(1)

        if self.iconName not in Images: Domoticz.Image('Chuangmi-icons.zip').Create()
        iconID = Images[self.iconName].ID

        if self.commandUnit not in Devices:
            Domoticz.Device(Name="Command",  Unit=self.commandUnit, TypeName="Selector Switch", Switchtype=18, Image=iconID, Options=self.commandOptions, Used=1).Create()

        DumpConfigToLog()
        Domoticz.Heartbeat(30)

        self.loadConfig()
        self.CreateDevices()
        Domoticz.Debug("onStart called")

    def onStop(self):
        Domoticz.Debug("onStop called")

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("onConnect called")

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called")

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

        if Unit == self.commandUnit:
            Domoticz.Debug('Handle Command Unit Commands')
            self.HandleCommandUnitCommands(Level)
            return

        Domoticz.Debug('Handle IR Commands')
        levelsList = self.data.get('Unit {0}'.format(Unit))
        Domoticz.Debug('Count levels: {0}'.format(len(levelsList)))

        for levels in levelsList:
            Domoticz.Debug('Record numbers {0}'.format(len(levels)))

            if Command == 'On' and levels.get('Level') == 10:
                IR_dict = dict(levels.get('LearnedCodes'))
                self.sendIRCommands(IR_dict)
                Devices[Unit].Update(nValue=1, sValue='On')

            elif Command == 'Off' and levels.get('Level') == 20:
                IR_dict = dict(levels.get('LearnedCodes'))
                self.sendIRCommands(IR_dict)
                Devices[Unit].Update(nValue=0, sValue='Off')

            elif Level == levels.get('Level'):
                IR_dict = dict(levels.get('LearnedCodes'))
                self.sendIRCommands(IR_dict)
                Devices[Unit].Update(nValue=Level, sValue='Set Level')

    def HandleCommandUnitCommands(self, Level):
        if self.commandUnit not in Devices:
            Domoticz.Error('Command device is required!')
            return

        Domoticz.Debug('Chuangmi address: '+str(Parameters['Address'])+' Token: '+str(Parameters['Mode1']))

        # Reset Level
        if Level == 10:
            self.lastLearnedIRCode = ''
            self.IRCodeCount = 0
            self.IR_dict.clear()
            Domoticz.Log('levels reset')

        # Learn Code
        if Level == 20:
           self.lastLearnedIRCode = self.learnIRCode()
           Domoticz.Debug('Learned Code: '+ str(self.lastLearnedIRCode))
           self.IRCodeCount += 1
           self.IR_dict['IRCode'+str(self.IRCodeCount)] = self.lastLearnedIRCode

        # Test IR Commands
        if Level == 30:
            if len(self.lastLearnedIRCode) == 0:
                Domoticz.Error('Command is required!')
                return

            self.sendIRCommands(self.IR_dict)

        # Save command
        if Level == 40:
            devicesCount = self.devicesCount + 1
            self.levelsCount += 10
            if self.levelsCount == 10: self.data['Unit '+str(devicesCount)] = []
            self.data['Unit '+str(devicesCount)].append({
                'Level': self.levelsCount,
                'LearnedCodes': self.IR_dict.copy()
                })

            #self.dumpConfig()
            self.IR_dict.clear()
            self.lastLearnedIRCode = ''
            self.IRCodeCount = 0
            Domoticz.Log('levels saved')

        # Create device
        if Level == 50:
            self.devicesCount += 1

            self.dumpConfig()
            self.CreateDevices()
            self.levelsCount = 0

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called")

    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat called")

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

    def CreateDevices(self):
        self.devicesCount = len(self.data)+1
        Domoticz.Debug('Total chuangmi devices: {0}'.format(self.devicesCount))

        for key in sorted(self.data):
            Domoticz.Debug('{0} was found'.format(key))

            levelsDict = self.data.get(key)
            Domoticz.Debug('Count levels: {0}'.format(len(levelsDict)))

            if int(key.strip('Unit ')) not in Devices:
                if len(levelsDict) == 1:
                    Domoticz.Device(Name=key, Unit=int(key.strip('Unit ')), Type=244, Switchtype=9, Subtype=73, Used=1).Create()
                    #Devices[int(key.strip('Unit '))].Update(nValue=0, sValue='Off')
                    Domoticz.Debug('Device {0} was created.'.format(key))
                elif len(levelsDict) == 2:
                    Domoticz.Device(Name=key, Unit=int(key.strip('Unit ')), Type=244, Switchtype=0, Subtype=73, Used=1).Create()
                    #Devices[int(key.strip('Unit '))].Update(nValue=0, sValue='Off')
                    Domoticz.Debug('Device {0} was created.'.format(key))
                else:
                    SelectorOptions =   {
                        "LevelActions"  :"|"*len(levelsDict),
                        "LevelNames"    :"Level|"*len(levelsDict)+"Level" ,
                        "LevelOffHidden":"true",
                        "SelectorStyle" :"0"
                    }

                    Domoticz.Device(Name=key,  Unit=int(key.strip('Unit ')), TypeName="Selector Switch", Switchtype=18, Image=12, Options=SelectorOptions, Used=1).Create()
                    #Devices[int(key.strip('Unit '))].Update(nValue=0, sValue='Off')
                    Domoticz.Debug('Device {0} was created.'.format(key))

        DumpConfigToLog()

    def learnIRCode(self):
        Domoticz.Debug('Learn command called')
        ir =  ChuangmiIr(Parameters['Address'],Parameters['Mode1'])
        ir.learn(key=1)

        learnedIRCode = ''
        timeout = 10

        while (len(learnedIRCode)==0) and (timeout > 0):
            time.sleep(1)
            timeout -= 1
            learnedIRCode = str(ir.read(key=1).get("code"))

        return learnedIRCode

    def sendIRCommands(self, IRCommands):
        ir =  ChuangmiIr(Parameters['Address'],Parameters['Mode1'])
        for key in sorted(IRCommands):
            Domoticz.Debug('IR Code: '+key)
            Domoticz.Debug(IRCommands.get(key))
            ir.play_raw(IRCommands.get(key),frequency='')
            time.sleep(0.100)

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
    return
