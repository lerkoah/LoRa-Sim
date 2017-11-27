import simpy
import random
import numpy as np
import math
import sys
import matplotlib.pyplot as plt
# %matplotlib inline
import os

from loraDir import frequencyCollision, sfCollision, powerCollision, airtime

# random.seed(123)
# check for collisions at base station
# Note: called before a packet (or rather node) is inserted into the list
def checkcollision(packet):
    col = 0 # flag needed since there might be several collisions for packet
    processing = 0
    for i in range(0,len(packetsAtBS)):
        if packetsAtBS[i].packet.processed == 1:
            processing = processing + 1
    if (processing > maxBSReceives):
        print "too long:", len(packetsAtBS)
        packet.processed = 0
    else:
        packet.processed = 1

    if packetsAtBS:
        print "CHECK node {} (sf:{} bw:{} freq:{:.6e}) others: {}".format(
             packet.nodeid, packet.sf, packet.bw, packet.freq,
             len(packetsAtBS))
        for other in packetsAtBS:
            if other.nodeid != packet.nodeid:
                print ">> node {} (sf:{} bw:{} freq:{:.6e})".format(
                   other.nodeid, other.packet.sf, other.packet.bw, other.packet.freq)
               # simple collision
                if frequencyCollision(packet, other.packet) and sfCollision(packet, other.packet):
                    if full_collision:
                        if timingCollision(packet, other.packet):
                           # check who collides in the power domain
                            c = powerCollision(packet, other.packet)
                           # mark all the collided packets
                           # either this one, the other one, or both
                            for p in c:
                                p.collided = 1
                                if p == packet:
                                    col = 1
                        else:
                           # no timing collision, all fine
                           pass
                    else:
                        packet.collided = 1
                        other.packet.collided = 1  # other also got lost, if it wasn't lost already
                        col = 1
        return col
    return 0

def transmit(env,node):
    while True:
        yield env.timeout(random.expovariate(1.0/float(node.period)))
#         yield env.timeout(np.random.exponential(1.0/float(node.period)))

        # time sending and receiving
        # packet arrives -> add to base station

        node.sent = node.sent + 1
        node.transmitionTime = node.transmitionTime + node.packet.rectime
        if (node in packetsAtBS):
            print "ERROR: packet already in"
        else:
            sensitivity = sensi[node.packet.sf - 7, [125,250,500].index(node.packet.bw) + 1]
            if node.packet.rssi < sensitivity:
                print "node {}: packet will be lost".format(node.nodeid)
                node.packet.lost = True
            else:
                node.packet.lost = False
                # adding packet if no collision
                if (checkcollision(node.packet)==1):
                    node.packet.collided = 1
                else:
                    node.packet.collided = 0
                packetsAtBS.append(node)
                node.packet.addTime = env.now

        yield env.timeout(node.packet.rectime)

        if node.packet.lost:
            global nrLost
            nrLost += 1
        if node.packet.collided == 1:
            global nrCollisions
            nrCollisions = nrCollisions +1
        if node.packet.collided == 0 and not node.packet.lost:
            global nrReceived
            nrReceived = nrReceived + 1
        if node.packet.processed == 1:
            global nrProcessed
            nrProcessed = nrProcessed + 1

        # complete packet has been received by base station
        # can remove it
        if (node in packetsAtBS):
            packetsAtBS.remove(node)
            # reset the packet
        node.packet.collided = 0
        node.packet.processed = 0
        node.packet.lost = False

def timingCollision(p1, p2):
    # assuming p1 is the freshly arrived packet and this is the last check
    # we've already determined that p1 is a weak packet, so the only
    # way we can win is by being late enough (only the first n - 5 preamble symbols overlap)

    # assuming 8 preamble symbols
    Npream = 8

    # we can lose at most (Npream - 5) * Tsym of our preamble
    Tpreamb = 2**p1.sf/(1.0*p1.bw) * (Npream - 5)

    # check whether p2 ends in p1's critical section
    p2_end = p2.addTime + p2.rectime
    p1_cs = env.now + Tpreamb
    print "collision timing node {} ({},{},{}) node {} ({},{})".format(
        p1.nodeid, env.now - env.now, p1_cs - env.now, p1.rectime,
        p2.nodeid, p2.addTime - env.now, p2_end - env.now
    )
    if p1_cs < p2_end:
        # p1 collided with p2 and lost
        print "not late enough"
        return True
    print "saved by the preamble"
    return False

# turn on/off graphics
graphics = 0

# do the full collision check
full_collision = False

# experiments:
# 0: packet with longest airtime, aloha-style experiment
# 0: one with 3 frequencies, 1 with 1 frequency
# 2: with shortest packets, still aloha-style
# 3: with shortest possible packets depending on distance



# this is an array with measured values for sensitivity
# see paper, Table 3
sf7 = np.array([7,-126.5,-124.25,-120.75])
sf8 = np.array([8,-127.25,-126.75,-124.0])
sf9 = np.array([9,-131.25,-128.25,-127.5])
sf10 = np.array([10,-132.75,-130.25,-128.75])
sf11 = np.array([11,-134.5,-132.75,-128.75])
sf12 = np.array([12,-133.25,-132.25,-132.25])
class myNode():
    def __init__(self, nodeid, bs, period, packetlen, x, y):
        self.nodeid = nodeid
        self.period = period
        self.bs = bs
        assert np.sqrt((x-bsx)**2+(y-bsy)**2) < maxDist, "Max distance error"
        self.x = x
        self.y = y

        self.dist = np.sqrt((self.x-bsx)*(self.x-bsx)+(self.y-bsy)*(self.y-bsy))
        print('node %d' %nodeid, "x", self.x, "y", self.y, "dist: ", self.dist)

#         self.packet = myPacket(self.nodeid, packetlen, self.dist)
        self.packet = None
        self.setPacket(packetlen)
        self.sent = 0

        # graphics for node
        global graphics
        if (graphics == 1):
            global ax
            ax.add_artist(plt.Circle((self.x, self.y), 2, fill=True, color='blue'))

        self.transmitionTime = 0

    def setPacket(self, packetlen):
        if self.packet != None:
            assert self.packet == None, "ERROR: Existing Packet association\nfrequency: {}; symTime: {}\nbw: {}; sf: {}; cr: {}; rssi: {}".format(self.packet.freq, self.packet.symTime,
                                                                                                             self.packet.bw, self.packet.sf, self.packet.cr, self.packet.rssi)
        self.packet = myPacket(self.nodeid, packetlen, self.dist)

#
# this function creates a packet (associated with a node)
# it also sets all parameters, currently random
#
class myPacket():
    def __init__(self, nodeid, plen, distance):
        global experiment
        global Ptx
        global gamma
        global d0
        global var
        global Lpld0
        global GL

        self.nodeid = nodeid
        self.txpow = Ptx

        # randomize configuration values
        self.sf = random.randint(6,12)
        self.cr = random.randint(1,4)
        self.bw = random.choice([125, 250, 500])

        # for certain experiments override these
        if experiment==1 or experiment == 0:
            self.sf = 12
            self.cr = 4
            self.bw = 125

        # for certain experiments override these
        if experiment==2:
            self.sf = 6
            self.cr = 1
            self.bw = 500
        # lorawan
        if experiment == 4:
            self.sf = 12
            self.cr = 1
            self.bw = 125


        # for experiment 3 find the best setting
        # OBS, some hardcoded values
        Prx = self.txpow  ## zero path loss by default

        # log-shadow
        Lpl = Lpld0 + 10*gamma*math.log10(distance/d0)
        print "Lpl:", Lpl
        Prx = self.txpow - GL - Lpl

        if (experiment == 3) or (experiment == 5):
            minairtime = 9999
            minsf = 0
            minbw = 0

            print "Prx:", Prx

            for i in range(0,6):
                for j in range(1,4):
                    if (sensi[i,j] < Prx):
                        self.sf = int(sensi[i,0])
                        if j==1:
                            self.bw = 125
                        elif j==2:
                            self.bw = 250
                        else:
                            self.bw=500
                        at = airtime(self.sf, 1, plen, self.bw)
                        if at < minairtime:
                            minairtime = at
                            minsf = self.sf
                            minbw = self.bw
                            minsensi = sensi[i, j]
            if (minairtime == 9999):
                print "does not reach base station"
                exit(-1)
            print "best sf:", minsf, " best bw: ", minbw, "best airtime:", minairtime
            self.rectime = minairtime
            self.sf = minsf
            self.bw = minbw
            self.cr = 1

            if experiment == 5:
                # reduce the txpower if there's room left
                self.txpow = max(2, self.txpow - math.floor(Prx - minsensi))
                Prx = self.txpow - GL - Lpl
                print 'minsesi {} best txpow {}'.format(minsensi, self.txpow)

        # transmission range, needs update XXX
        self.transRange = 150
        self.pl = plen
        self.symTime = (2.0**self.sf)/self.bw
        self.arriveTime = 0
        self.rssi = Prx
        # frequencies: lower bound + number of 61 Hz steps
        self.freq = 860000000 + self.bw*random.randint(0,64)*1e3

#         # for certain experiments override these and
#         # choose some random frequences
#         if experiment == 1:
#             self.freq = random.choice([860000000, 864000000, 868000000])
#         else:
#             self.freq = 860000000

        print "frequency" ,self.freq, "symTime ", self.symTime
        print "bw", self.bw, "sf", self.sf, "cr", self.cr, "rssi", self.rssi
        self.rectime = airtime(self.sf,self.cr,self.pl,self.bw)
        print "rectime node ", self.nodeid, "  ", self.rectime
        # denote if packet is collided
        self.collided = 0
        self.processed = 0

# nrNodes = 100
nrNodesList = range(0,510,10)
nrNodesList[0] = 1
iteration = 10
for it in range(iteration):
    for nrNodes in nrNodesList:
        avgSendTime = 15*60*1000
        experiment = 4
        simtime = 7*24*60*60*1000

        full_collision = False

        print "Nodes:", nrNodes
        print "AvgSendTime (exp. distributed):",avgSendTime
        print "Experiment: ", experiment
        print "Simtime: ", simtime
        print "Full Collision: ", full_collision

        # global stuff
        #Rnd = random.seed(12345)
        nodes = []
        packetsAtBS = []
        env = simpy.Environment()

        # maximum number of packets the BS can receive at the same time
        maxBSReceives = 8


        # max distance: 300m in city, 3000 m outside (5 km Utz experiment)
        # also more unit-disc like according to Utz
        bsId = 1
        nrCollisions = 0
        nrReceived = 0
        nrProcessed = 0
        nrLost = 0

        Ptx = 14
        gamma = 2.08
        d0 = 40.0
        var = 0           # variance ignored for now
        Lpld0 = 127.41
        GL = 0

        sensi = np.array([sf7,sf8,sf9,sf10,sf11,sf12])
        if experiment in [0,1,4]:
            minsensi = sensi[5,2]  # 5th row is SF12, 2nd column is BW125
        elif experiment == 2:
            minsensi = -112.0   # no experiments, so value from datasheet
        elif experiment in [3,5]:
            minsensi = np.amin(sensi) ## Experiment 3 can use any setting, so take minimum
        Lpl = Ptx - minsensi
        print "amin", minsensi, "Lpl", Lpl
        maxDist = d0*(math.e**((Lpl-Lpld0)/(10.0*gamma)))
        print "maxDist:", maxDist

        # base station placement
        bsx = maxDist+10
        bsy = maxDist+10
        xmax = bsx + maxDist + 20
        ymax = bsy + maxDist + 20

        # prepare graphics and add sink
        if (graphics == 1):
            plt.ion()
            plt.figure()
            ax = plt.gcf().gca()
            # XXX should be base station position
            ax.add_artist(plt.Circle((bsx, bsy), 3, fill=True, color='green'))
            ax.add_artist(plt.Circle((bsx, bsy), maxDist, fill=False, color='green'))

        for i in range(0,nrNodes):
            # this is very complex prodecure for placing nodes
            # and ensure minimum distance between each pair of nodes
            found = 0
            rounds = 0
            while (found == 0 and rounds < 100):
                a = random.random()
                b = random.random()
                if b<a:
                    a,b = b,a
                posx = b*maxDist*np.cos(2*math.pi*a/b)+bsx
                posy = b*maxDist*np.sin(2*math.pi*a/b)+bsy
                if len(nodes) > 0:
                    for index, n in enumerate(nodes):
                        dist = np.sqrt(((abs(n.x-posx))**2)+((abs(n.y-posy))**2))
                        if dist >= 10:
                            found = 1
                        else:
                            rounds = rounds + 1
                            if rounds == 100:
                                print "could not place new node, giving up"
                                exit(-1)
                else:
                    print "first node"
                    found = 1

            # myNode takes period (in ms), base station id packetlen (in Bytes)
            # 1000000 = 16 min
            node = myNode(i,bsId, avgSendTime,20, posx, posy)
            nodes.append(node)
            env.process(transmit(env,node))

        #prepare show
        if (graphics == 1):
            plt.xlim([0, xmax])
            plt.ylim([0, ymax])
            plt.draw()
            plt.show()

        # start simulation
        env.run(until=simtime)
        print("----------------------------")
        print("----------------------------")

        # print stats and save into file
        print "nrCollisions ", nrCollisions

        # compute energy
        # Transmit consumption in mA from -2 to +17 dBm
        TX = [22, 22, 22, 23,                                      # RFO/PA0: -2..1
              24, 24, 24, 25, 25, 25, 25, 26, 31, 32, 34, 35, 44,  # PA_BOOST/PA1: 2..14
              82, 85, 90,                                          # PA_BOOST/PA1: 15..17
              105, 115, 125]                                       # PA_BOOST/PA1+PA2: 18..20
        # mA = 90    # current draw for TX = 17 dBm
        V = 3.0     # voltage XXX
        sent = sum(n.sent for n in nodes)
        energy = sum(node.packet.rectime * TX[int(node.packet.txpow)+2] * V * node.sent for node in nodes) / 1e6
        timeTotal = sum(n.transmitionTime for n in nodes)


        print "energy (in J): ", energy
        print "sent packets: ", sent
        print "collisions: ", nrCollisions
        print "received packets: ", nrReceived
        print "processed packets: ", nrProcessed
        print "lost packets: ", nrLost
        print "Total time to fly: ", timeTotal

        # data extraction rate
        der = (sent-nrCollisions)/float(sent)
        print "DER:", der
        der = (nrReceived)/float(sent)
        print "DER method 2:", der

        # this can be done to keep graphics visible
        if (graphics == 1):
            raw_input('Press Enter to continue ...')
        print("----------------------------")
        print("Saving at"),
        # save experiment data into a dat file that can be read by e.g. gnuplot
        # name of file would be:  exp0.dat for experiment 0
        fname = "exp" + str(experiment) + ".dat"
        print fname+'...',
        if os.path.isfile(fname):
            res = "\n" + str(nrNodes) + " " + str(nrCollisions) + " "  + str(sent) + " " + str(energy) + " " + str(nrReceived) + " " + str(nrProcessed) + " " + str(timeTotal)
        else:
            res = "#nrNodes nrCollisions nrTransmissions OverallEnergy nrReceived nrProcessed timeToFly\n" + str(nrNodes) + " " + str(nrCollisions) + " "  + str(sent) + " " + str(energy) + " " + str(nrReceived) + " " + str(nrProcessed) + " " + str(timeTotal)
        with open(fname, "a") as myfile:
            myfile.write(res)
        myfile.close()
        print('done.')
        print("----------------------------")
        print("----------------------------")
        # with open('nodes.txt','w') as nfile:
        #     for n in nodes:
        #         nfile.write("{} {} {}\n".format(n.x, n.y, n.nodeid))
        # with open('basestation.txt', 'w') as bfile:
        #     bfile.write("{} {} {}\n".format(bsx, bsy, 0))
