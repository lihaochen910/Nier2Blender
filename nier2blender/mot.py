import numpy
import struct
from io import IOBase

class MOT(object):
	pass

class HermitKeyframe(object):

	def __init__(self, frameIndex, coeffs):
		self.frameIndex = frameIndex
		self.coeffs = coeffs
		self.p = coeffs[0]
		self.a = coeffs[1]
		self.d = coeffs[2]

	def __str__(self):
		return "frame=%d, %g, %g, %g" % (self.frameIndex, self.coeffs[0], self.coeffs[1],
                                   self.coeffs[2])


class HermitSpline(object):

	def __init__(self, keyframes):
		self.keyframes = keyframes

	def eval(self, frameIndex):
		if frameIndex <= self.keyframes[0].frameIndex:
			return self.keyframes[0].p
		if frameIndex >= self.keyframes[-1].frameIndex:
			return self.keyframes[-1].p
		i_ = 0
		for i, k in enumerate(self.keyframes):
			if frameIndex < k.frameIndex:
				i_ = i - 1
				break
			if frameIndex == k.frameIndex:
				return k.p
		k1 = self.keyframes[i_]
		k2 = self.keyframes[i_ + 1]

		t = 1.0 * (frameIndex - k1.frameIndex) / (k2.frameIndex - k1.frameIndex)
		tt = t * t
		ttt = tt * t
		v = (2 * ttt - 3 * t + 1) * k1.p + (ttt - 2 * tt + t) * \
                    k1.d + (-2 * ttt + 3 * tt) * k2.p + (ttt - tt) * k2.a
		return v


class PlainKeyframe(object):

	def __init__(self, frameIndex, value):
		self.frameIndex = frameIndex
		self.value = value

	def __str__(self):
		return "frame=%d, %g" % (self.frameIndex, self.value)


class PlainSpline(object):

	def __init__(self, keyframes):
		self.keyframes = keyframes

	def eval(self, frameIndex):
		if frameIndex <= self.keyframes[0].frameIndex:
			return self.keyframes[0].value
		if frameIndex >= self.keyframes[-1].frameIndex:
			return self.keyframes[-1].value
		return self.keyframes[frameIndex].value


class Track(object):
	def read(self, mot):
		self.bone_id = mot.get("h")
		# 0-POSX 1-POSY 2-POSZ 3-ROTX 4-ROTY 5-ROTZ 7-SCALEX 8-SCALEY 9-SCALEZ
		self.type = mot.get("B")
		self.comtype = mot.get("B")  # compress type
		self.keycount = mot.get("I")  # keyframe count
		if self.comtype == self.keycount == 0:
			self.const = mot.get("f")
			self.is_const = True
			self.offset = 0x0
		else:
			self.offset = mot.get("I")  # whence=os.SEEK_CUR
			self.const = 0.0
			self.is_const = False

		self.spline = None

	# just as Bayonetta2, offset is relative
	def adjust_offset(self, offset):
		if self.offset > 0:
			self.offset += offset

	def parse_keyframes(self, mot):
		if self.offset <= 0:
			return
		C = FloatDecompressor(6, 9, 47)

		mot.seek(self.offset)
		if self.comtype == 1:
			keyframe_data = []
			for i in range(self.keycount):
				value = mot.get("f")
				keyframe = PlainKeyframe(i, value)
				keyframe_data.append(keyframe)
				print (str(keyframe))

			self.spline = PlainSpline(keyframe_data)

		elif self.comtype == 2:  # 2 float + 1 unsigned short
			values = mot.get("2f")
			keyframe_data = []
			for i in range(self.keycount):
				value = values[0] + values[1] * mot.get("H")
				keyframe = PlainKeyframe(i, value)
				keyframe_data.append(keyframe)
				print (str(keyframe))
			self.spline = PlainSpline(keyframe_data)

		elif self.comtype == 3:
			values = []
			for v in mot.get("2H"):
				values.append(C.decompress(v))
			keyframe_data = []
			for i in range(self.keycount):
				value = values[0] + values[1] * mot.get("B")
				keyframe = PlainKeyframe(i, value)
				keyframe_data.append(keyframe)
				print (str(keyframe))

			self.spline = PlainSpline(keyframe_data)

		elif self.comtype == 4:
			keyframe_data = []
			for i in range(self.keycount):
				values = mot.get("HHfff")
				frameIndex = values[0]
				assert values[1] == 0, "this is padding"
				keyframe = HermitKeyframe(frameIndex, values[2:])
				keyframe_data.append(keyframe)
				print (str(keyframe))

			self.spline = HermitSpline(keyframe_data)

		elif self.comtype == 5:
			values = list(mot.get("6f"))
			keyframe_data = []

			for i in range(self.keycount):
				params = mot.get("4H")
				frameIndex = params[0]
				coeffs = [values[0] + params[1] * values[1],
                                    values[2] + params[2] * values[3],
                                    values[4] + params[3] * values[5]]
				keyframe = HermitKeyframe(frameIndex, coeffs)
				keyframe_data.append(keyframe)
				print (str(keyframe))

			self.spline = HermitSpline(keyframe_data)

		elif self.comtype == 6:
			# values as [base1, extent1],[base2, extent2],[base3, extent3]
			raw = mot.get_raw(0xc)
			print ("raw = ", map(hex, struct.unpack("HHHHHH", raw)))

			values = []
			for v in struct.unpack("6H", raw):
				values.append(C.decompress(v))
			print ("values =", values)
			# print ("floatDecompressor", values)
            #
            #
			# values = numpy.frombuffer(raw, dtype=numpy.dtype("<f2"))
			keyframe_data = []
			for i in range(self.keycount):
				params = mot.get("4B")

				frameIndex = params[0]
				coeffs = [values[0] + params[1] * values[1],
                                    values[2] + params[2] * values[3],
                                    values[4] + params[3] * values[5]]
				keyframe = HermitKeyframe(frameIndex, coeffs)
				keyframe_data.append(keyframe)
				print (str(keyframe))

			self.spline = HermitSpline(keyframe_data)
		elif self.comtype == 7:
			# values as [base1, extent1],[base2, extent2],[base3, extent3]
			raw = mot.get_raw(0xc)
			print ("raw = ", map(hex, struct.unpack("HHHHHH", raw)))

			values = []
			for v in struct.unpack("6H", raw):
				values.append(C.decompress(v))
			print ("values =", values)
			# print ("floatDecompressor", values)
            #
            #
			# values = numpy.frombuffer(raw, dtype=numpy.dtype("<f2"))
			keyframe_data = []
			frameIndex = 0
			for i in range(self.keycount):
				params = mot.get("4B")

				frameCount = params[0]
				frameIndex += frameCount
				coeffs = [values[0] + params[1] * values[1],
                                    values[2] + params[2] * values[3],
                                    values[4] + params[3] * values[5]]
				keyframe = HermitKeyframe(frameIndex, coeffs)
				keyframe_data.append(keyframe)
				print (str(keyframe))

			self.spline = HermitSpline(keyframe_data)
		elif self.comtype == 8:
			# values as [base1, extent1],[base2, extent2],[base3, extent3]
			raw = mot.get_raw(0xc)
			print ("raw = ", map(hex, struct.unpack("HHHHHH", raw)))

			values = []
			for v in struct.unpack("6H", raw):
				values.append(C.decompress(v))
			print ("values =", values)
			# print ("floatDecompressor", values)
            #
            #
			# values = numpy.frombuffer(raw, dtype=numpy.dtype("<f2"))
			keyframe_data = []
			for i in range(self.keycount):
				params = mot.get("H3B")

				frameIndex = params[0]
				coeffs = [values[0] + params[1] * values[1],
                                    values[2] + params[2] * values[3],
                                    values[4] + params[3] * values[5]]
				keyframe = HermitKeyframe(frameIndex, coeffs)
				keyframe_data.append(keyframe)
				print (str(keyframe))

			self.spline = HermitSpline(keyframe_data)
		else:
			assert False, ("unknown compress type %d" % self.comtype)

	def eval(self, frameIndex):
		if self.is_const:
			return self.const
		return self.spline.eval(frameIndex)

	def __str__(self):
		ret = "Bone:%d, type=%d, compress=%d, keynum=%d, " % (
			self.bone_id, self.type, self.comtype, self.keycount)
		if self.is_const:
			ret += "value = %f" % self.const
		else:
			ret += "offset = 0x%x" % self.offset
		return ret

#thanks Phernost (stackoverflow)
class FloatDecompressor(object):
	significandFBits = 23
	exponentFBits = 8
	biasF = 127
	exponentF = 0x7F800000
	significandF = 0x007fffff
	signF = 0x80000000
	signH = 0x8000

	def __init__(self, eHBits, sHBits, bH):
		self.exponentHBits = eHBits
		self.significandHBits = sHBits
		self.biasH = bH

		self.exponentH = ((1 << eHBits) - 1) << sHBits
		self.significandH = (1 << sHBits) - 1

		self.shiftSign = self.significandFBits + self.exponentFBits - \
			self.significandHBits - self.exponentHBits
		self.shiftBits = self.significandFBits - self.significandHBits

	def decompress(self, value):
		ui = value
		sign = ui & self.signH
		ui ^= sign

		sign <<= self.shiftSign
		exponent = ui & self.exponentH
		significand = ui ^ exponent
		significand <<= self.shiftBits

		si = sign | significand
		magic = 1.0
		if exponent == self.exponentH:
			si |= self.exponentF
		elif exponent != 0:
			exponent >>= self.significandHBits
			exponent += self.biasF - self.biasH
			exponent <<= self.significandFBits
			si |= exponent
		elif significand != 0:
			magic = (2 * self.biasF - self.biasH) << self.significandFBits
			magic = struct.unpack("f", struct.pack("I", magic))[0]
		f = struct.unpack("f", struct.pack("I", si))[0]
		f *= magic
		return f

# makes parsing data a lot easier
def get_getter(data, endian):
	return getter(data, endian)

class getter(object):

	def __init__(self, data, endian):
		self.data = data
		self.endian = endian
		self.is_file = isinstance(self.data, IOBase)
		if self.is_file:
			self.offset = self.data.tell()
			self.data.seek(0, 2)
			self.size = self.data.tell()
			self.data.seek(0, self.offset)
		else:
			self.offset = 0
			self.size = len(data)

	def seek(self, offset, whence=0):
		assert whence in (0, 1, 2)
		if self.is_file:
			self.data.seek(offset, whence)
			self.offset = self.data.tell()
		else:
			if whence == 0:
				self.offset = offset
			elif whence == 1:
				self.offset += offset
			elif whence == 2:
				self.offset = len(self.data) - offset

	def skip(self, size):
		self.seek(size, 1)

	def pad(self, size, pad_pattern="\x00"):
		pad_data = self.get_raw(size)
		pattern_size = len(pad_pattern)
		for i in range(size / pattern_size):
			assert pad_pattern.startswith(
				pad_data[i * pattern_size: (i + 1) * pattern_size])

	def align(self, size):
		rem = self.offset % size
		if rem:
			self.pad(size - rem)

	def get_raw(self, size):
		if self.is_file:
			data_seg = self.data.read(size)
		else:
			data_seg = self.data[self.offset: self.offset + size]
		self.offset += size
		return data_seg

	def get(self, fmt, offset=None, force_tuple=False):
		if offset is not None:
			self.seek(offset)
		size = struct.calcsize(fmt)
		data_seg = self.get_raw(size)
		res = struct.unpack(self.endian + fmt, data_seg)
		if not force_tuple and len(res) == 1:
			return res[0]
		return res

	def get_cstring(self):
		s = ""
		ch = ""
		while ch != "\x00":
			ch = self.get_raw(1)
			s += ch
		return s.rstrip("\x00")

	def block(self, size, endian=None):
		data = self.get_raw(size)
		if endian is None:
			endian = self.endian
		return getter(data, endian)

	def assert_end(self):
		assert self.offset == self.size
