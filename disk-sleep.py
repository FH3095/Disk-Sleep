#!/usr/bin/env python3

import argparse
import time
import os
import sys
import subprocess
VERSION = '1.0'
HDPARM = 'hdparm'
DISKSTATS = '/proc/diskstats'
ARGS = None

#ARGS = ['--timeout=25',"/dev/sda",'/dev/sdb']
#HDPARM = r'E:\Program Files\!Portable\Git\usr\bin\ls.exe'
#DISKSTATS = 'diskstats.txt'

class Disk(object):
    def __init__(self,path,timeout,standby):
        self.name = os.path.basename(os.path.realpath(path))
        self.path = path
        self.lastSectorsRead = 0
        self.lastSectorsWritten = 0
        self.timeout = int(timeout)
        self.nextTimeout = int(time.time()) + self.timeout
        self.isStandby = False
        self.lastStandbyStart = 0
        if standby >= 0 and standby <= 255:
            proc = subprocess.run([HDPARM, '-S', str(standby), self.path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300, text=True)
            if proc.returncode != 0:
                print("Cant set drive timeout. hdparm exited with "+str(proc.returncode)+": "+str(proc.stdout), file=sys.stderr)
        print("Monitoring "+self.name+"("+self.path+") with timeout "+str(self.timeout)+" and drive-standby "+str(standby))
    def updateAndCheckTimeoutReached(self,disks):
        if not self.name in disks:
            print("Cant find diskstats-entry for "+self.name+" in "+str(disks), file=sys.stderr)
            return False
        disk = disks[self.name]
        if self.lastSectorsRead != disk['sectors_read'] or self.lastSectorsWritten != disk['sectors_written']:
            self.lastSectorsRead = disk['sectors_read']
            self.lastSectorsWritten = disk['sectors_written']
            self.nextTimeout = int(time.time()) + self.timeout
            if self.isStandby:
                print(self.name+" restarted")
                self.isStandby = False
            return False
        elif self.isStandby:
            return False
        elif self.nextTimeout < time.time():
            return True
        else:
            return False
    def sendToStandby(self):
        print("Sending "+self.name+" to standby. Last standby was "+time.ctime(self.lastStandbyStart))
        self.lastStandbyStart = time.time()
        proc = subprocess.run([HDPARM, '-y', self.path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300, text=True)
        if proc.returncode != 0:
            print("Cant send disk to standyby. hdparm exited with "+str(proc.returncode)+": "+str(proc.stdout), file=sys.stderr)
        self.updateAndCheckTimeoutReached(readDiskStats())
        self.isStandby = True


def parseArguments(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', action='version', version='%(prog)s '+VERSION)
    parser.add_argument('-t', '--timeout', dest='timeout', default=10800, type=int, help='Send disks to standby after seconds')
    parser.add_argument('-s', '--drive-standby', dest='standby', default=-1, type=int, help='Set disk timeout via hdparm -S, if number is >= 0')
    parser.add_argument('disks', nargs='+', metavar='disk', help='Disks to send to standby')
    result = parser.parse_args(args)
    return result

def createDiskList(diskPaths,timeout,standby):
    result = []
    stats = readDiskStats()
    for diskPath in diskPaths:
        diskObj = Disk(diskPath, timeout, standby)
        diskObj.updateAndCheckTimeoutReached(stats)
        result.append(diskObj)
    return tuple(result)

def readDiskStats():
    columns = [
        '_major_number', '_minor_number', 'name',
        '_reads', '_reads_merged', 'sectors_read', '_time_reading',
        '_writes', '_writes_merged', 'sectors_written', 'time_writing'
    ]
    result = {}
    with open(DISKSTATS, mode='rt') as statsFile:
        for line in statsFile:
            lineParts = line.split()
            if len(lineParts) < len(columns):
                continue
            data = dict(tuple(zip(columns, lineParts)))
            result[data['name']] = {}
            for k,v in data.items():
                if k == 'name':
                    continue
                result[data['name']][k] = int(v)
    return result


print("Wait 2 minutes before detecting drives")
time.sleep(120) # Wait 2 minutes to give linux time to detect all disks

args = parseArguments(ARGS)
disks = createDiskList(args.disks, int(args.timeout), int(args.standby))
sleepTime = int(args.timeout / 100) # Sleep 1% of disk timeout time.
if sleepTime < 1:
    sleepTime = 1


while True:
    time.sleep(sleepTime)
    stats = readDiskStats()
    for disk in disks:
        if disk.updateAndCheckTimeoutReached(stats):
            disk.sendToStandby()
