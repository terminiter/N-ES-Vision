import sys, os, cv, cv2, math, glob, csv
import numpy as np
import scipy as sp
from scipy import signal
from PIL import Image, ImageOps
from collections import Counter
from ssim import SSIM
from ssim.utils import get_gaussian_kernel
from scipy.stats import norm

import networkx as nx

def AABBOverlap(rect1, rect2, printIt = False):

	#Rectangle defined by rect1
	r1left = int(rect1[0])
	r1right = r1left + int(rect1[1])
	r1bottom = int(rect1[2])
	r1top = r1bottom + int(rect1[3])

	#Rectangle defined by rect2
	r2left = int(rect2[0])
	r2right = r2left + int(rect2[1])
	r2bottom = int(rect2[2])
	r2top = r2bottom + int(rect2[3])
	distanceThreshold = 2
	if  (r1left - r2right <  distanceThreshold and r2left -  r1right <  distanceThreshold  and 
		r1bottom - r2top < distanceThreshold and r2bottom-r1top < distanceThreshold) :
		left = abs(r1left - r2right)
		right = abs(r1right-r2left)
		up = abs(r1top-r2bottom)
		down = abs(r1bottom-r2top)
		if down < left and down < right and down < up:
			return 'down'
		if up < left and up < right:
			return 'up'
		if  left < right:
			return 'left'
		return 'right'

	else:
		return False

if __name__ == '__main__':
	FFMPEG_BIN = "ffmpeg" # Use on Linux ans Mac OS
	#FFMPEG_BIN = "ffmpeg.exe" # Use on Windows


	import yaml
	inputfile = sys.argv[1]
	with open(inputfile,'rb') as f:
		inputfile = yaml.load(f)


	spritesDirectory = inputfile['spritesDirectory']
	frameInformation = inputfile['frameCSV']

	folder = inputfile['frameFolder']
	distanceScale = inputfile['distanceScale']
	creationCost = inputfile['creationCost']
	deletionCost = inputfile['deletionCost']
	missGate = inputfile['missGate']
	minTrackLength = inputfile['minTrackLength']
	movingProbThreshold = inputfile['movingProbThreshold']
	edgeGuard = inputfile['edgeGuard']

	for frameFile in glob.glob(folder+"*.png"):
		frameImage = cv2.imread(frameFile)
		break

	directory = "./"+spritesDirectory+"/"

	sprites = {}
	for filename in glob.glob(directory+"*.png"):
		sprite_gray =ImageOps.grayscale(Image.open(filename))
		sprites[filename] = sprite_gray


	gaussian_kernel_sigma = 1.5
	gaussian_kernel_width = 11
	gaussian_kernel_1d = get_gaussian_kernel(gaussian_kernel_width, gaussian_kernel_sigma)

	matching = {}
	maxVal = float('-inf')
	for sprite1 in sprites:
		matching[sprite1]  = {}
		for sprite2 in sprites:
			matching[sprite1][sprite2] = SSIM(sprites[sprite1], gaussian_kernel_1d).ssim_value(sprites[sprite2])#np.max(sp.signal.correlate2d(sprites[sprite1],sprites[sprite2]))
			if matching[sprite1][sprite2] > maxVal:
				maxVal = matching[sprite1][sprite2]

	for s1 in matching:
		for s2 in matching[s1]:
			matching[s1][s2] /= maxVal
			#print s1, s2, matching[s1][s2]

	frames = []
	with open(frameInformation) as frameData:
		categories = frameData.readline().rstrip().split(',')
		curFrame = -1
		frame = None
		for line in frameData:
			dat = line.rstrip().split(',')
			if int(dat[0]) != curFrame:
				if frame:
					frames.append(frame)
				curFrame = int(dat[0])
				frame = []
			frame.append(dat)
	frames.append(frame)
	tracks = {}
	curTrack = 0
	ids2Track = {}
	activeTracks = []
	trackMisses = {}
	xs = []
	ys = []
	import os.path
	import pickle
	fname = frameInformation + '_{}{}{}{}.pkl'.format(distanceScale,creationCost,deletionCost,missGate)
	if os.path.isfile(fname):
		tracks = pickle.load( open(fname, "rb" ) )
		for tID, track in tracks.items():
			for pt in track:
				xs.append(pt[2])
				ys.append(pt[3])
	else:
		for spC,ci in zip(frames[0],range(len(frames[0]))):
			sprite =spC[1]
			x = float(spC[2])
			y = float(spC[3])
			track = [(0,sprite,x,y)]
			ids2Track[(0,ci)] = curTrack
			tracks[curTrack] = track
			trackMisses[curTrack] = 0
			activeTracks.append(curTrack)
			curTrack += 1
			xs.append(x)
			ys.append(y)
		scaleValue = 1.0/norm.pdf(0,scale=distanceScale)
		powValue = 1.0
		for fID in range(1,len(frames)):
			sys.stderr.write('{}\n'.format(float(fID)/float(len(frames))))
			pID = fID - 1
			G = nx.DiGraph()
			for trackID in activeTracks:
				trackWeight = pow(min(1,creationCost+float(1+len(tracks[trackID]))/minTrackLength),powValue)
				lastPt = tracks[trackID][-1]
				sprite1 = lastPt[1]
				x1 = lastPt[2]
				y1 = lastPt[3]
				G.add_edge('p{}'.format(trackID),'c{}Deletion'.format(trackID),weight=deletionCost)
				for spC,ci in zip(frames[fID],range(len(frames[fID]))):
					sprite2 =spC[1]
					if   matching[directory+sprite1][directory+sprite2] > 0.1 :
						x2 = float(spC[2])
						y2 = float(spC[3])
						xs.append(x2)
						ys.append(y2)
						if abs(x2-x1) < sprites[directory+sprite1].size[0]*2 and abs(y2-y1) < sprites[directory+sprite1].size[1]*2: 
							px = norm.pdf(x1-x2,scale=distanceScale)*scaleValue
							py = norm.pdf(y1-y2,scale=distanceScale)*scaleValue
							weight = px*py*trackWeight* pow(matching[directory+sprite1][directory+sprite2],0.5)
							
							G.add_edge('p{}'.format(trackID),'c{}'.format(ci),weight=weight)

			for spC,ci in zip(frames[fID],range(len(frames[fID]))):
				G.add_edge('c{}Creation'.format(ci),'c{}'.format(ci),weight=creationCost)
			match = nx.algorithms.max_weight_matching(G)	
			'''
			G = nx.DiGraph()
			for spP,pi in zip(frames[pID],range(len(frames[pID]))):
				print spP
				for spC,ci in zip(frames[fID],range(len(frames[fID]))):
					sprite1 =spP[1]
					sprite2 =spC[1]
					x1 = float(spP[2])
					y1 = float(spP[3])
					x2 = float(spC[2])
					y2 = float(spC[3])
					px = norm.pdf(x1-x2,scale=distanceScale)/norm.pdf(0,scale=distanceScale)
					py = norm.pdf(y1-y2,scale=distanceScale)/norm.pdf(0,scale=distanceScale)
					weight = matching[directory+sprite1][directory+sprite2]*px*py
					
					G.add_edge('p{}'.format(pi),'c{}'.format(ci),weight=weight)

			for spP,pi in zip(frames[pID],range(len(frames[pID]))):
				G.add_edge('p{}'.format(pi),'c{}Deletion'.format(pi),weight=deletionCost)
			for spC,ci in zip(frames[fID],range(len(frames[fID]))):
				G.add_edge('c{}Creation'.format(ci),'c{}'.format(ci),weight=creationCost)
			match = nx.algorithms.max_weight_matching(G)	
			'''
			alreadySeen = set()
			for p1,p2 in match.items():

				if p1 in alreadySeen or p2 in alreadySeen:
					continue
				alreadySeen.add(p1)
				alreadySeen.add(p2)
				if 'p' in p2 or 'Creation' in p2:
					temp = p2
					p2 = p1
					p1 = temp
				if 'Creation' in p1 :
					track = []
					#ids2Track[(fID,int(p2[1:]))] = curTrack
					tracks[curTrack] = track
					x = float(frames[fID][int(p2[1:])][2])
					y = float(frames[fID][int(p2[1:])][3])
					track.append((fID,frames[fID][int(p2[1:])][1],x,y))
					tracks[curTrack] = track
					activeTracks.append(curTrack)
					trackMisses[curTrack] = 0
					curTrack += 1
					
				elif 'Deletion' in p2:
					#trackID = ids2Track[(pID,int(p1[1:]))]
					trackID = int(p1[1:])
					trackMisses[trackID] += 1
					if trackMisses[trackID] > missGate:
						activeTracks.remove(trackID)
					else:
						track = tracks[trackID]
						pt = list(track[-1])
						pt[0] = fID
						pt.append('coast')
						pt = tuple(pt)
						track.append(pt)
				else:
					x = float(frames[fID][int(p2[1:])][2])
					y = float(frames[fID][int(p2[1:])][3])
					#trackID = ids2Track[(pID,int(p1[1:]))]
					trackID = int(p1[1:])
					#ids2Track[(fID,int(p2[1:]))] = trackID
					track = tracks[trackID]
					track.append((fID, frames[fID][int(p2[1:])][1],x,y))
					trackMisses[trackID] = 0
		pickle.dump(tracks, open( fname, "wb" ) )

	#if the end of a track is coasting, go to the last actual point in the track as the end of the track
	for trackID, track in tracks.items():
		lastIndex = len(track)
		for ii in range(len(track)-1,-1,-1):
			if track[ii][-1] != 'coast':
				lastIndex = ii+1
				break
		track = track[:lastIndex]
		tracks[trackID] = track

	timeTracks = {}
	for trackID, track in tracks.items():
		timeTracks[trackID] = {}
		for state in track:
			timeTracks[trackID][state[0]] = state
	events = {}
	timeline = {}

	for trackID, track in tracks.items():
		for state in track:
			time = state[0]
			if time not in timeline:
				timeline[time] = []
			timeline[time].append(trackID)
	trackVelocities = {}
	lastTime = -1
	for time in range(0,len(frames)):
		prevTime = time-1
		if len(timeline[time]) > 0:
			lastTime = time
		for trackID in timeline[time]:
			cx = timeTracks[trackID][time][2]
			cy = timeTracks[trackID][time][3]
			px = cx
			py = cy
			if prevTime in timeTracks[trackID]:
				px = timeTracks[trackID][prevTime][2]
				py = timeTracks[trackID][prevTime][3]
			vx = cx-px
			vy = cy-py

			if trackID not in trackVelocities:
				trackVelocities[trackID] = {}
			trackVelocities[trackID][time] = (vx,vy)

	for time in range(1,len(frames)):	
		vxs = []
		vys = []
		for trackID in timeline[time]:
			vxs.append(trackVelocities[trackID][time][0])
			vys.append(trackVelocities[trackID][time][1])
		medX = Counter(vxs).most_common(1)[0][0]
		medY = Counter(vys).most_common(1)[0][0]
		#medX = np.median(np.array(vxs))
		#medY = np.median(np.array(vys))
		for trackID in timeline[time]:
			#print (medX,medY),trackVelocities[trackID][time],(trackVelocities[trackID][time][0]-medX,trackVelocities[trackID][time][1]-medY )
			trackVelocities[trackID][time] = (trackVelocities[trackID][time][0]-medX,trackVelocities[trackID][time][1]-medY )
	trackVelocities2 = {}
	window = inputfile['velMedianWindow']
	window = range(-(window/2),1+window/2) #[-2,-1,0,edgeGuard]
	
	for track in trackVelocities:
		trackVelocities2[track] = {}

		for time in trackVelocities[track]:
			vxs = []
			vys = []
			for offset in window:
				if time-offset in trackVelocities[track]:
					vxs.append(trackVelocities[track][time-offset][0])
					vys.append(trackVelocities[track][time-offset][1])
			
			rollingvx = np.median(np.array(vxs))
			rollingvy = np.median(np.array(vys))
			trackVelocities2[track][time] = (rollingvx,rollingvy)

	trackVelocities = trackVelocities2

	probabilityOfMoving = {}
	for trackID, track in tracks.items():
		for state in track:
			time = state[0]
			sprite = state[1]
			if sprite not in probabilityOfMoving:
				probabilityOfMoving[sprite] = {'Y':0,'N':0}
			if abs(trackVelocities[trackID][time][0]) > 0 or abs(trackVelocities[trackID][time][1]) > 0:
				probabilityOfMoving[sprite]['Y'] += 1
			else:
				probabilityOfMoving[sprite]['N'] += 1
	for sprite in probabilityOfMoving:
		#print sprite,float(probabilityOfMoving[sprite]['Y'])/float(probabilityOfMoving[sprite]['Y']+probabilityOfMoving[sprite]['N'])
		probabilityOfMoving[sprite] = float(probabilityOfMoving[sprite]['Y'])/float(probabilityOfMoving[sprite]['Y']+probabilityOfMoving[sprite]['N'])
		
	minX = 0
	minY = 0
	maxX = frameImage.shape[1]
	maxY = frameImage.shape[0]
	with open(fname+'Velocities','wb') as velfile:
		for trackID, track in tracks.items():
			for state in track:
				velfile.write('{},{},{},{},{}\n'.format(state[0],state[2],state[3],trackVelocities[trackID][state[0]][0],trackVelocities[trackID][state[0]][1]))
	
	causes = {}
	opposite = {'left':'right',
				'right':'left',
				'up':'down',
				'down':'up'}
	for trackID, track in tracks.items():
		if len(track) > minTrackLength:
			for state in track:
				time = state[0]
				width =  sprites[directory+state[1]].size[0]
				height = sprites[directory+state[1]].size[1]
				rect1 = (state[2],width,state[3],height)
				for otherTrack in timeline[time]:
					if otherTrack != trackID:
						otherState = timeTracks[otherTrack][time]
						otherWidth =  sprites[directory+otherState[1]].size[0]
						otherHeight = sprites[directory+otherState[1]].size[1]
						rect2 = (otherState[2],otherWidth,otherState[3],otherHeight)
						overlap = AABBOverlap(rect1,rect2)
						if overlap:
							if time not in causes:
								causes[time] = set()
							causes[time].add((trackID,otherTrack,overlap))
							causes[time].add((otherTrack,trackID,opposite[overlap]))
	for trackID, track in tracks.items():
		if len(track) > minTrackLength:
			if track[0][0] != 0:
				width = edgeGuard*sprites[directory+track[0][1]].size[0]
				height = edgeGuard*sprites[directory+track[0][1]].size[1]
				if abs(track[0][2]-minX) > width and abs(track[0][2]-maxX) > width and abs(track[0][3]-minY) > height and abs(track[0][3]-maxY) > height: 
					if track[0][0] not in events:
						events[track[0][0]] = []
					events[track[0][0]].append( ('C',track[0][1],trackID))
			
			width = edgeGuard*sprites[directory+track[-1][1]].size[0]
			height = edgeGuard*sprites[directory+track[-1][1]].size[1]
			if  track[-1][0] != lastTime:
				if abs(track[-1][2]-minX) > width and abs(track[-1][2]-maxX) > width and abs(track[-1][3]-minY) > height and abs(track[-1][3]-maxY) > height: 
					if track[-1][0] not in events:
						events[track[-1][0]] = []
					events[track[-1][0]].append( ('D',track[-1][1],trackID))
			prevState = None
			prevTime = None
			for state in track:

				time = state[0]
				if prevState and prevState != state[1]:
					if time not in events:
						events[time] = []
					events[time].append(('S',prevState,state[1],trackID))
				if probabilityOfMoving[state[1]] > movingProbThreshold:
					if prevTime:
						vx = trackVelocities[trackID][time][0]
						vy = trackVelocities[trackID][time][1]
						pvx = trackVelocities[trackID][prevTime][0]
						pvy = trackVelocities[trackID][prevTime][1]
						#print time,state[1],pvx,pvy,vx,vy
						if np.sign(vx) != np.sign(pvx) and abs(pvx) > 0 and vx == 0.0:
							if time not in events:
								events[time] = []
							events[time].append(('VX',state[1],trackID))
						if np.sign(vy) != np.sign(pvy) and abs(pvy) > 0 and vy == 0 :
							if time not in events:
								events[time] = []
							events[time].append(('VY',state[1],trackID))

				prevState = state[1]
				prevTime = time
	#print events
	collisionWindow = 2
	displayWindow = 3
	validCollisions = {}
	reportedCollisions = {}
	for time in range(1,len(frames)):	
		validCollisions[time] = set()
		reportedCollisions[time] = set()
		for offset in range(displayWindow):
			if time -offset in validCollisions:
				for coll in validCollisions[time-offset]:
					if time in timeTracks[coll[3]] and time in timeTracks[coll[4]]:
						reportedCollisions[time].add(coll) # print time,coll[0],coll[1],coll[2]
		if time in causes:
			for cause in causes[time]:
				causeStr = (timeTracks[cause[0]][time][1],timeTracks[cause[1]][time][1],cause[2])
				good = False
				for offset in range(1,collisionWindow):
					if time-offset in causes:
						foundIt = False
						for otherCause in causes[time-offset]:
							otherCauseStr = (timeTracks[otherCause[0]][time-offset][1],timeTracks[otherCause[1]][time-offset][1],otherCause[2])
								
							if cause == otherCause or causeStr == otherCauseStr:
								foundIt = True
						good = not foundIt or good
						if good:
							break
					else: 
						good = True
						break
				if good:
					validCollisions[time].add((timeTracks[cause[0]][time][1],timeTracks[cause[1]][time][1],cause[2],cause[0],cause[1]))
					#print time,timeTracks[cause[0]][time][1],timeTracks[cause[1]][time][1],cause[2]
					reportedCollisions[time].add( (timeTracks[cause[0]][time][1],timeTracks[cause[1]][time][1],cause[2],cause[0],cause[1]))
			''' if (time) in events:
				for event in events[time]:
					eventStr = ''
					for e in event:
						eventStr += '{} '.format(e) 
					print time, eventStr
			'''

	fname = frameInformation + '_{}{}{}{}.CEPairs'.format(distanceScale,creationCost,deletionCost,missGate)
	with open(fname,'wb') as outfile:
		outfile.write('ObjectA,ObjectB,A2BDir,EffectType,Source,Target,Which\n')
		for time in reportedCollisions:
			for collision in reportedCollisions[time]:
				if time in events:
					for event in events[time]:
						#Mario,GROUND,D,VelChange,Mario,None,A
						other = 'None'
						if len(event) == 4:
							other = event[3]
						who = 'Other'
						if event[2] == collision[3]:
							who = "A"
						if event[2] == collision[4]:
							who = "B"
						outfile.write('{},{},{},{},{},'.format(collision[0],collision[1],collision[2],event[0],event[1],other)+who +'\n')
				else:
					outfile.write('{},{},{},{},{},{}\n'.format(collision[0],collision[1],collision[2],'None','None','None'))
