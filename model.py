from collections import defaultdict, Counter
import math

class Model(object):

	@staticmethod
	def load(path):
		import cPickle
		try:
			with open(path, 'rb') as inputFile:
				return cPickle.load(inputFile)
		except cPickle.UnpickleableError as e:
			raise IOError("Unable to read model from the given file.", e)
		except cPickle.UnpicklingError as e:
			raise IOError("Unable to read model from the given file.", e)

	def save(self, path):
		import cPickle
		with open(path, 'wb') as outputFile:
			cPickle.dump(self, outputFile, protocol = cPickle.HIGHEST_PROTOCOL)

	defaultLayout = r'''

 * * * *   * * * *
00 1 2 33 44 5 6 77777

~! @ # $% ^& * ( )_+<
`1 2 3 45 67 8 9 0-=

 Q W E RT YU I O P{}|>
 q w e rt yu i o p[]\

^A S D FG HJ K L :"
 a s d fg hj k l ;'    <=

 Z X C VB NM < > ?
 z x c vb nm , . /

	'''

	# With index finger in home position being 1.0, how hard is it to press each key?
	# Costs aren't symmetric, because in my case it's different for each hand, and
	# keyboards tend to have slanted columns (e.g. N is easier to press than B).
	keyCost = [list(map(float, l.strip().split())) for l in [l for l in '''

|---Pinky|Ring|-Mid-|Index--|  |--Index|-Mid-|Ring|Pinky------------------|

12.0 10.0  3.0  3.0  4.0  4.0  4.5  3.0  3.0  3.0 12.0 16.0 18.0 20.0
      8.0  2.2  1.5  1.6  2.5  3.0  1.6  1.5  2.2  8.0 10.0 12.0 16.0 24.0
 8.0  4.0  2.0  1.5  1.0  1.4  1.4  1.0  1.5  2.0  4.0  8.0
      5.0  4.0  3.0  1.2  2.5  2.0  1.2  3.0  4.0  6.0

	'''.splitlines() if l.strip()][1:]]

	defaultLayoutLines = tuple(line for line in defaultLayout.splitlines() if line.strip())

	fingerAssignment = tuple(int(character) if character != ' ' else None for character in defaultLayoutLines[1])
	verticalHome = (iter(index / 2 for index, line in enumerate(defaultLayoutLines[2:]) if line.strip()[-2:] == '<=').next(),) * 8
	horizontalHome = tuple(index for index, character in enumerate(defaultLayoutLines[0]) if character == '*')

	backspace = '\b'   # ASCII for backspace
	delete = '\x7F'    # ASCII for delete
	capsLock = '\x01'  # Some unique ascii code because there isn't one for caps lock.

	specialCharacterToString = {
		backspace: '< ',
		delete: '> ',
		capsLock: '^ ',
	}

	stringToSpecialCharacter = dict((value, key) for key, value in specialCharacterToString.items())

	def _stringToLayout(stringToSpecialCharacter, s):
		def alignLines(upper, lower):
			for u, l in zip(upper + ' ' * min(max(0, len(lower) - len(upper)), 3), lower + ' ' * min(max(0, len(upper) - len(lower)), 3)):
				if not str.isspace(u) or not str.isspace(l):
					yield u, l

		lines = [line for line in s.splitlines() if line.strip()]
		return tuple(
			tuple(
				upperChar + lowerChar if lowerChar != ' ' else stringToSpecialCharacter[upperChar + lowerChar] + ' '
				for upperChar, lowerChar in alignLines(upperLine, lowerLine)
			)
			for upperLine, lowerLine in zip(lines[::2], lines[1::2])
		)

	defaultLayoutRows = _stringToLayout(stringToSpecialCharacter, '\n'.join(defaultLayoutLines[2:]))
	layoutColumnMap = tuple(tuple(line.index(character) for character in line.strip() if character != ' ') for line in defaultLayoutLines[2::2])
	inverseLayoutColumnMap = dict(((r, layoutColumn), c) for r, row in enumerate(layoutColumnMap) for c, layoutColumn in enumerate(row))

	# Base costs measure how much we'd prefer to be using the index finger over the given finger.
	# They should match the cost of pressing home-position keys.	
	baseCost = [keyCost[verticalHome[finger]][inverseLayoutColumnMap[(verticalHome[finger], horizontalHome[finger])]] for finger in range(len(verticalHome))]

	_stringToLayout = staticmethod(_stringToLayout)

	@classmethod
	def stringToLayout(cls, s):
		return cls._stringToLayout(cls.stringToSpecialCharacter, s)

	@classmethod
	def displayLayout(cls, layout):
		lines = []
		for i in range(len(layout)*3-1):
			line = []
			if i % 3 < 2:
				if (i / 3) % 2 == 1:
					line.append(' ')
				for key in layout[i/3]:
					if key[0] in cls.specialCharacterToString:
						key = cls.specialCharacterToString[key[0]] + ' '
					line.append(key[i%3])
			lines.append(line)
		return '\n'.join(map(''.join, lines))

	@classmethod
	def displayLayoutSimple(cls, layout):
		return '\n'.join(''.join(x[1] if x[0] not in cls.specialCharacterToString else cls.specialCharacterToString[x[0]][0] for x in (line if i % 2 == 1 else ('  ',) + line)) for i, line in enumerate(layout[1:]))

	@classmethod
	def typeCost(cls, layoutRow, layoutCol):
		return cls.keyCost[layoutRow][layoutCol]

	@classmethod
	def _bigramCost(cls, (row1, col1), (row2, col2)):
		layoutCol1 = cls.layoutColumnMap[row1][col1]
		finger1 = cls.fingerAssignment[layoutCol1]
		layoutCol2 = cls.layoutColumnMap[row2][col2]
		finger2 = cls.fingerAssignment[layoutCol2]
		if finger1 > finger2:
			finger1, finger2 = finger2, finger1 # we don't care about order of presses
			row1, row2 = row2, row1
			col1, col2 = col2, col1
			layoutCol1, layoutCol2 = layoutCol2, layoutCol1
		
		# These costs should be a bit less extreme than the single finger costs.
		# This is achieved by regressing the cost toward the base cost for each finger.
		cost = 0.3 * (cls.baseCost[finger1] + cls.baseCost[finger2]) + 0.7 * (cls.typeCost(row1, col1) + cls.typeCost(row2, col2))

		if finger1 == finger2: return 4. * cost # same finger
		if finger1 < 4 and finger2 >= 4: return 0.8 * cost # different hands
		
		# same hand. penalize difficult arrangements
		
		# make everything left-hand
		if finger1 >= 4:
			finger1 = 7 - finger1
			finger2 = 7 - finger2
		if finger1 > finger2:
			finger1, finger2 = finger2, finger1 # we don't care about order of presses
			row1, row2 = row2, row1
			col1, col2 = col2, col1
			layoutCol1, layoutCol2 = layoutCol2, layoutCol1

		layoutColumnDistance = abs(layoutCol1 - layoutCol2)

		if finger1 == 0 and finger2 == 3:
			# It's not very nice if we're using index and pinky.
			# It's even worse if the hand is stretched apart.
			# In layout space:
			# - 6 columns is the distance between the home positions.
			# - 7 columns means the index finger is moved, but the pinky isn't.
			# - >7 columns means the pinky is stretched.
			return 1.5 * cost if layoutColumnDistance <= 6 else 2. * cost if layoutColumnDistance <= 7 else 3. * cost

		if finger1 == 0:
			# Other pinky cases.
			if row1 == row2 - 2: return cost
			if row1 == row2 - 1: return 0.9 * cost
			if row1 == row2: return 1.1 * cost
			if row1 == row2 + 1: return 1.6 * cost
			return 3. * cost

		if finger2 == 3:
			# Index finger cases, where it's not index and pinky.
			indexFingerInHomeColumn = (layoutCol2 == cls.horizontalHome[cls.fingerAssignment[layoutCol2]])
			
			if row2 == row1 + 1:
				return 0.7 * cost if indexFingerInHomeColumn else 1.3 * cost
			if row2 == row1:
				return 0.9 * cost if indexFingerInHomeColumn else 1.2 * cost

			if row2 == row1 - 1:
				if finger1 == 1: return 1.5 * cost
				return 1.8 * cost if indexFingerInHomeColumn else 1.5 * cost # it's easier in this case if the index finger isn't in its home row

			if row2 == row1 + 2:
				return 1.2 * cost if indexFingerInHomeColumn else 1.8 * cost
			
			# The remaining options are pretty bad.
			return 2.5 * cost

		# must be middle and ring finger now
		if row1 == row2: return 0.8 * cost
		if row1 == row2 - 1: return 1.2 * cost
		if row1 == row2 + 1: return 1.5 * cost
		return 2.5 * cost

	def populateBigramLookup(self):
		self.bigramCostLookup = tuple(
			self._bigramCost((r1, c1), (r2, c2))
			for r1 in range(len(self.defaultLayoutRows))
			for c1 in range(len(self.defaultLayoutRows[r1]))
			for r2 in range(len(self.defaultLayoutRows))
			for c2 in range(len(self.defaultLayoutRows[r2]))
		)

		r2l = [0]
		for r in self.defaultLayoutRows:
			r2l.append(len(r) + r2l[-1])

		c1m = r2l[-1]

		r1l = [0]
		for r in self.defaultLayoutRows:
			r1l.append(len(r) * c1m + r1l[-1])

		self._r2l = tuple(r2l)
		self._c1m = c1m		
		self._r1l = tuple(r1l)

	def bigramCost(self, (row1, col1), (row2, col2)):
		return self.bigramCostLookup[self._r1l[row1] + self._c1m * col1 + self._r2l[row2] + col2]

	@classmethod
	def bigramDebug(cls, R, C):
		print '\n'.join(
			' '.join(('%02.2f' % cls._bigramCost((R, C), (row, col))).rjust(5) if col >= 0 else ' '*5 for col in r)
			for row, r in enumerate([range(14), range(-1,14), range(0,12), range(-1,10)]))

	@classmethod
	def costDebug(cls):
		print '\n'.join(
			' '.join(('%02.2f' % cls.typeCost(row,col)).rjust(5) if col >= 0 else ' '*5 for col in r)
			for row, r in enumerate([range(14), range(-1,14), range(0,12), range(-1,10)]))


	# We want to add in counts for the usage of backspace, delete, and caps lock.
	# This is done by assuming said keys are a certain proportion of typing.
	backspaceProportion = 1. / 100.
	deleteProportion = 1. / 200.
	capsLockProportion = 0.

	@classmethod
	def adjustCounts(cls, counts):
		newCounts = Counter()
		totalCount = 0
		for c, count in counts.items():
			newCounts[c] = count
			totalCount += count

		newCounts[cls.backspace] = int(math.ceil(cls.backspaceProportion * totalCount))
		newCounts[cls.delete] = int(math.ceil(cls.deleteProportion * totalCount))
		newCounts[cls.capsLock] = int(math.ceil(cls.capsLockProportion * totalCount))

		return newCounts

	@classmethod
	def adjustBigramCounts(cls, counts):
		newCounts = Counter()
		chars = set()
		totalCount = 0
		for b, count in counts.items():
			newCounts[b] = count
			totalCount += count
			for c in b:
				chars.add(c)

		halfTotalCount = (totalCount + 1) / 2
		for c in chars:
			newCounts[cls.backspace + c] = newCounts[c + cls.backspace] = int(math.ceil(cls.backspaceProportion * halfTotalCount / len(chars)))
			newCounts[cls.delete + c] = newCounts[c + cls.delete] = int(math.ceil(cls.deleteProportion * halfTotalCount / len(chars)))
			newCounts[cls.capsLock + c] = newCounts[c + cls.capsLock] = int(math.ceil(cls.capsLockProportion * halfTotalCount / len(chars)))

		return newCounts

	def __init__(self, lines):
		self.populateBigramLookup()

		allowedCharacters = set(c for row in self.defaultLayoutRows for col in row for c in col) | set(' \t\n')

		from ngrams import ngramCounts
		self.counts = self.adjustCounts(ngramCounts(1, (c for line in lines for c in line if c in allowedCharacters)))
		self.bigrams = self.adjustBigramCounts(ngramCounts(2, (c for line in lines for c in line if c in allowedCharacters)))

		self.totalCharacters = sum(self.counts.values())
		self.characterWeighting = 1.0 / self.totalCharacters if self.totalCharacters != 0 else 0.0

		# Taking 2500 bigrams captures the vast majority of typed bigram weight, including all of the backspace and delete bigrams.
		self.importantBigrams = tuple(sorted((count, bigram) for bigram, count in self.bigrams.items() if bigram[0] != bigram[1] and all(c not in bigram for c in ' \t\n'))[::-1][:2500])

		# Bigrams duplicate everything, hence the divide-by-2 in the weighting.
		self.bigramWeighting = 1.0 / (sum(count for count, bigram in self.importantBigrams) * 2.0)

		#print '\n'.join('%s %d' % (bigram, count) for count, bigram in self.importantBigrams)

	def __call__(self, layout, simplicity = 0.0):
		cells = [(row, col) for row in range(len(layout)) for col in range(len(layout[row]))]
		lookup = dict((c, (row, col)) for row, col in cells for c in layout[row][col])
		
		fingerWork = [0. for i in range(8)]
		for r, c in cells:
			c1, c2 = layout[r][c]
			fingerWork[self.fingerAssignment[self.layoutColumnMap[r][c]]] += self.typeCost(r, c) * ((self.counts[c1] if c1 != ' ' else 0.) + (self.counts[c2] if c2 != ' ' else 0.))

		averageFingerWork = self.characterWeighting * sum(fingerWork) / 8.0
		worstFingerWork = self.characterWeighting * max(fingerWork)

		if simplicity > 0.75:
			# Might as well approximate while the component for bigrams is small.
			return (0.1 + 0.9 * simplicity) * averageFingerWork + 0.9 * (1.0 - simplicity) * worstFingerWork

		bigramAverageFingerWork = self.bigramWeighting * sum(self.bigramCost(lookup[c1], lookup[c2]) * count for count, (c1, c2) in self.importantBigrams)

		return (0.1 + 0.9 * simplicity) * averageFingerWork + 0.9 * (1.0 - simplicity) * (0.3 * worstFingerWork + 0.7 * bigramAverageFingerWork)
			

class Layouts(object):
	QWERTY = Model.stringToLayout(r'''
		~!@#$%^&*()_+<
		`1234567890-=

		QWERTYUIOP{}|>
		qwertyuiop[]\

		^ASDFGHJKL:"
		 asdfghjkl;'

		ZXCVBNM<>?
		zxcvbnm,./
	''')

	DVORAK = Model.stringToLayout(r'''
		~!@#$%^&*(){}<
		`1234567890[]
		
		"<>PYFGCRL?+|>
		',.pyfgcrl/=\
		
		^AOEUIDHTNS_
		 aoeuidhtns-

		:QJKXBMWVZ
		;qjkxbmwvz
	''')

	PDVORAK = Model.stringToLayout(r'''
		~%7531902468`<
		$&[{}(=*)+]!#
		
		:<>PYFGCRL?^|>
		;,.pyfgcrl/@\
		
		^AOEUIDHTNS_
		 aoeuidhtns-

		"QJKXBMWVZ
		'qjkxbmwvz
	''')

	COLEMAK = Model.stringToLayout(r'''
		~!@#$%^&*()_+<
		`1234567890-=

		QWFPGJLUY:[]\>
		qwfpgjluy;{}|

		^ARSTDHNEIO"
		 arstdhneio'

		ZXCVBKM<>?
		zxcvbkm,./
	''')

	WORKMAN = Model.stringToLayout(r'''
		~!@#$%^&*()_+<
		`1234567890-=

		QDRWBJFUP:{}|>
		qdrwbjfup;[]\

		^ASHTGYNEOI"
		 ashtgyneoi'

		ZXMCVKL<>?
		zxmcvkl,./
	''')

	ALPHA = Model.stringToLayout(r'''
		~$0123456789^<
		`*/{[(=+)]}\%

		_GSNFAEMLYQ|@>
		-gsnfaemlyq&#

		^BODHPUITR:"
		 bodhpuitr;'

		ZXCVWJK<>?
		zxcvwjk,.!
	''')

	BETA = Model.stringToLayout(r'''
		~$0123456789^<
		`*/{[(=+)]}\%

		_NSDULTIOGQ|@>
		-nsdultiogq&#

		^YBRHFPMEA:"
		 ybrhfpmea;'

		ZXCVWJK<>?
		zxcvwjk,.!
	''')

	GAMMA = Model.stringToLayout(r'''
		~$0123456789^<
		`*/{[(=+)]}\%

		_FSTPLNIOYQ|@>
		-fstplnioyq&#

		^BURDGHMEA:"
		 burdghmea;'

		ZXCVWJK<>?
		zxcvwjk,.!
	''')

	DELTA = Model.stringToLayout(r'''
		~$0123456789^<
		`*/{[(=+)]}\%

		_FDGBRNIOMQ|@>
		-fdgbrniomq&#

		^YUSTPHLEA:"
		 yustphlea;'

		ZXCVWJK<>?
		zxcvwjk,.!
	''')

	EPSILON = Model.stringToLayout(r'''
		~$0123456789^<
		`*/{[(=+)]}\%

		_FBRLDTIOGQ|@>
		-fbrldtiogq&#

		^:USNHPMEA"Y
		 ;usnhpmea'y

		ZXCVWJK<>?
		zxcvwjk,.!
	''')

	THETA = Model.stringToLayout(r'''
		~$0123456789^<
		`*/{[(=+)]}\%

		_BPNLMTOUGQ|@>
		-bpnlmtougq&#

		^:SIRHFDEA"Y
		 ;sirhfdea'y

		ZXCVWJK<>?
		zxcvwjk,.!
	''')

	OMEGA = Model.stringToLayout(r'''
		^?0123456789$~
		%!/{[(=+)]}\*`

		 <>SMFWUIOK_|@^
		 ,.smfwuiok-&#

		:BLRNPGTEAYQ
		;blrnpgteayq

		 ZXCVHJD"<>
		 zxcvhjd'
	''')

	OMEGA3 = Model.stringToLayout(r'''
		^?0123456789$~
		%!/{[(=+)]}\*`

		 <>SMFYUPGKJ|@^
		 ,.smfyupgkj&#

		:BLDNROEITWQ
		;bldnroeitwq

		 ZXCVH_A"<>
		 zxcvh-a'
	''')

	OMEGA6 = Model.stringToLayout(r'''
		^?0123456789$~
		%!/{[(=+)]}\*`

		 <>SMFUAPTY_|@^
		 ,.smfuapty-&#

		:BLRNHOEIDGQ
		;blrnhoeidgq

		 ZXCVWJK"<>
		 zxcvwjk'
	''')

	OMEGA9 = Model.stringToLayout(r'''
		^?0123456789$~
		%!/{[(=+)]}\*`

		 KRSMF"UGPJ_|@^
		 krsmf'ugpj-&#

		:BLDNHOETIYQ
		;bldnhoetiyq

		 ZXCV<>AW<>
		 zxcv,.aw
	''')

	layouts = {
		'QWERTY': QWERTY,
		'DVORAK': DVORAK,
		'PDVORAK': PDVORAK,
		'COLEMAK': COLEMAK,
		'WORKMAN': WORKMAN,
		'ALPHA': ALPHA,
		'BETA': BETA,
		'GAMMA': GAMMA,
		'DELTA': DELTA,
		'EPSILON': EPSILON,
		'THETA': THETA,
		'OMEGA': OMEGA,
		'OMEGA3': OMEGA3,
		'OMEGA6': OMEGA6,
		'OMEGA9': OMEGA9,
	}




if __name__ == '__main__':
	from sys import argv, stdin, stderr

	incorrectArguments = False
	saveLocation = None

	if len(argv) > 1 and argv[1] not in ('-l', '-s'):
		incorrectArguments = True
	elif len(argv) > 1 and len(argv) < 3:
		incorrectArguments = True
	elif len(argv) > 3 and (len(argv) != 5 or argv[3] not in ('-l', '-s')):
		incorrectArguments = True

	elif '-l' not in argv:
		model = Model(list(stdin))
	else:
		path = argv[argv.index('-l') + 1]
		try:
			model = Model.load(path)
		except IOError as ex:
			print "Unable to load model from the given path.", ex
			print
			incorrectArguments = True
		
	if not incorrectArguments:
		if '-s' in argv:
			path = argv[argv.index('-s') + 1]
			model.save(path)

		for name, layout in Layouts.layouts.items():
			print name, model(layout)

	if incorrectArguments:
		stderr.write(
			'Invalid arguments given.\n\n' + 
			' Usage: %s [-l savedModelLocation] [-s modelLocation]\n' % argv[0] +
			'With no parameters, computes costs of known keyboard layouts for a corpus given on standard input.\n' +
			'"-l savedModelLocation" will instead load a saved model from the given path.\n' +
			'"-s modelLocation" will save the model to the given path.')
