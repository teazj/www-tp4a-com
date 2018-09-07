#
# The Python Imaging Library.
# $Id$
#
# BMP file handler
#
# Windows (and OS/2) native bitmap storage format.
#
# history:
# 1995-09-01 fl   Created
# 1996-04-30 fl   Added save
# 1997-08-27 fl   Fixed save of 1-bit images
# 1998-03-06 fl   Load P images as L where possible
# 1998-07-03 fl   Load P images as 1 where possible
# 1998-12-29 fl   Handle small palettes
# 2002-12-30 fl   Fixed load of 1-bit palette images
# 2003-04-21 fl   Fixed load of 1-bit monochrome images
# 2003-04-23 fl   Added limited support for BI_BITFIELDS compression
#
# Copyright (c) 1997-2003 by Secret Labs AB
# Copyright (c) 1995-2003 by Fredrik Lundh
#
# See the README file for information on usage and redistribution.
#


from PIL import Image, ImageFile, ImagePalette, _binary
import math

__version__ = "0.7"

i8 = _binary.i8
i16 = _binary.i16le
i32 = _binary.i32le
o8 = _binary.o8
o16 = _binary.o16le
o32 = _binary.o32le

#
# --------------------------------------------------------------------
# Read BMP file

BIT2MODE = {
    # bits => mode, rawmode
    1: ("P", "P;1"),
    4: ("P", "P;4"),
    8: ("P", "P"),
    16: ("RGB", "BGR;15"),
    24: ("RGB", "BGR"),
    32: ("RGB", "BGRX"),
}


def _accept(prefix):
    return prefix[:2] == b"BM"


# ==============================================================================
# Image plugin for the Windows BMP format.
# ==============================================================================
class BmpImageFile(ImageFile.ImageFile):
    """ Image plugin for the Windows Bitmap format (BMP) """

    # -------------------------------------------------------------- Description
    format_description = "Windows Bitmap"
    format = "BMP"
    # --------------------------------------------------- BMP Compression values
    COMPRESSIONS = {'RAW': 0, 'RLE8': 1, 'RLE4': 2, 'BITFIELDS': 3, 'JPEG': 4, 'PNG': 5}
    RAW, RLE8, RLE4, BITFIELDS, JPEG, PNG = 0, 1, 2, 3, 4, 5

    def _bitmap(self, header=0, offset=0):
        """ Read relevant info about the BMP """
        read, seek = self.fp.read, self.fp.seek
        if header:
            seek(header)
        file_info = dict()
        file_info['header_size'] = i32(read(4))  # read bmp header size @offset 14 (this is part of the header size)
        file_info['direction'] = -1
        # --------------------- If requested, read header at a specific position
        header_data = ImageFile._safe_read(self.fp, file_info['header_size'] - 4)  # read the rest of the bmp header, without its size
        # --------------------------------------------------- IBM OS/2 Bitmap v1
        # ------ This format has different offsets because of width/height types
        if file_info['header_size'] == 12:
            file_info['width'] = i16(header_data[0:2])
            file_info['height'] = i16(header_data[2:4])
            file_info['planes'] = i16(header_data[4:6])
            file_info['bits'] = i16(header_data[6:8])
            file_info['compression'] = self.RAW
            file_info['palette_padding'] = 3
        # ---------------------------------------------- Windows Bitmap v2 to v5
        elif file_info['header_size'] in (40, 64, 108, 124):  # v3, OS/2 v2, v4, v5
            if file_info['header_size'] >= 40:  # v3 and OS/2
                file_info['y_flip'] = i8(header_data[7]) == 0xff
                file_info['direction'] = 1 if file_info['y_flip'] else -1
                file_info['width'] = i32(header_data[0:4])
                file_info['height'] = i32(header_data[4:8]) if not file_info['y_flip'] else 2**32 - i32(header_data[4:8])
                file_info['planes'] = i16(header_data[8:10])
                file_info['bits'] = i16(header_data[10:12])
                file_info['compression'] = i32(header_data[12:16])
                file_info['data_size'] = i32(header_data[16:20])  # byte size of pixel data
                file_info['pixels_per_meter'] = (i32(header_data[20:24]), i32(header_data[24:28]))
                file_info['colors'] = i32(header_data[28:32])
                file_info['palette_padding'] = 4
                self.info["dpi"] = tuple(
                    map(lambda x: int(math.ceil(x / 39.3701)),
                        file_info['pixels_per_meter']))
                if file_info['compression'] == self.BITFIELDS:
                    if len(header_data) >= 52:
                        for idx, mask in enumerate(['r_mask', 'g_mask', 'b_mask', 'a_mask']):
                            file_info[mask] = i32(header_data[36+idx*4:40+idx*4])
                    else:
                        # 40 byte headers only have the three components in the bitfields masks,
                        # ref: https://msdn.microsoft.com/en-us/library/windows/desktop/dd183376(v=vs.85).aspx
                        # See also https://github.com/python-pillow/Pillow/issues/1293
                        # There is a 4th component in the RGBQuad, in the alpha location, but it
                        # is listed as a reserved component, and it is not generally an alpha channel
                        file_info['a_mask'] = 0x0
                        for mask in ['r_mask', 'g_mask', 'b_mask']:
                            file_info[mask] = i32(read(4))
                    file_info['rgb_mask'] = (file_info['r_mask'], file_info['g_mask'], file_info['b_mask'])
                    file_info['rgba_mask'] = (file_info['r_mask'], file_info['g_mask'], file_info['b_mask'], file_info['a_mask'])
        else:
            raise IOError("Unsupported BMP header type (%d)" % file_info['header_size'])
        # ------------------ Special case : header is reported 40, which
        # ---------------------- is shorter than real size for bpp >= 16
        self.size = file_info['width'], file_info['height']
        # -------- If color count was not found in the header, compute from bits
        file_info['colors'] = file_info['colors'] if file_info.get('colors', 0) else (1 << file_info['bits'])
        # -------------------------------- Check abnormal values for DOS attacks
        if file_info['width'] * file_info['height'] > 2**31:
            raise IOError("Unsupported BMP Size: (%dx%d)" % self.size)
        # ----------------------- Check bit depth for unusual unsupported values
        self.mode, raw_mode = BIT2MODE.get(file_info['bits'], (None, None))
        if self.mode is None:
            raise IOError("Unsupported BMP pixel depth (%d)" % file_info['bits'])
        # ----------------- Process BMP with Bitfields compression (not palette)
        if file_info['compression'] == self.BITFIELDS:
            SUPPORTED = {
                32: [(0xff0000, 0xff00, 0xff, 0x0), (0xff0000, 0xff00, 0xff, 0xff000000), (0x0, 0x0, 0x0, 0x0)],
                24: [(0xff0000, 0xff00, 0xff)],
                16: [(0xf800, 0x7e0, 0x1f), (0x7c00, 0x3e0, 0x1f)]
            }
            MASK_MODES = {
                (32, (0xff0000, 0xff00, 0xff, 0x0)): "BGRX",
                (32, (0xff0000, 0xff00, 0xff, 0xff000000)): "BGRA",
                (32, (0x0, 0x0, 0x0, 0x0)): "BGRA",
                (24, (0xff0000, 0xff00, 0xff)): "BGR",
                (16, (0xf800, 0x7e0, 0x1f)): "BGR;16",
                (16, (0x7c00, 0x3e0, 0x1f)): "BGR;15"
            }
            if file_info['bits'] in SUPPORTED:
                if file_info['bits'] == 32 and file_info['rgba_mask'] in SUPPORTED[file_info['bits']]:
                    raw_mode = MASK_MODES[(file_info['bits'], file_info['rgba_mask'])]
                    self.mode = "RGBA" if raw_mode in ("BGRA",) else self.mode
                elif file_info['bits'] in (24, 16) and file_info['rgb_mask'] in SUPPORTED[file_info['bits']]:
                    raw_mode = MASK_MODES[(file_info['bits'], file_info['rgb_mask'])]
                else:
                    raise IOError("Unsupported BMP bitfields layout")
            else:
                raise IOError("Unsupported BMP bitfields layout")
        elif file_info['compression'] == self.RAW:
            if file_info['bits'] == 32 and header == 22:  # 32-bit .cur offset
                raw_mode, self.mode = "BGRA", "RGBA"
        else:
            raise IOError("Unsupported BMP compression (%d)" % file_info['compression'])
        # ---------------- Once the header is processed, process the palette/LUT
        if self.mode == "P":  # Paletted for 1, 4 and 8 bit images
            # ----------------------------------------------------- 1-bit images
            if not (0 < file_info['colors'] <= 65536):
                raise IOError("Unsupported BMP Palette size (%d)" % file_info['colors'])
            else:
                padding = file_info['palette_padding']
                palette = read(padding * file_info['colors'])
                greyscale = True
                indices = (0, 255) if file_info['colors'] == 2 else list(range(file_info['colors']))
                # ------------------ Check if greyscale and ignore palette if so
                for ind, val in enumerate(indices):
                    rgb = palette[ind*padding:ind*padding + 3]
                    if rgb != o8(val) * 3:
                        greyscale = False
                # -------- If all colors are grey, white or black, ditch palette
                if greyscale:
                    self.mode = "1" if file_info['colors'] == 2 else "L"
                    raw_mode = self.mode
                else:
                    self.mode = "P"
                    self.palette = ImagePalette.raw("BGRX" if padding == 4 else "BGR", palette)

        # ----------------------------- Finally set the tile data for the plugin
        self.info['compression'] = file_info['compression']
        self.tile = [('raw', (0, 0, file_info['width'], file_info['height']), offset or self.fp.tell(),
                      (raw_mode, ((file_info['width'] * file_info['bits'] + 31) >> 3) & (~3), file_info['direction'])
                      )]

    def _open(self):
        """ Open file, check magic number and read header """
        # read 14 bytes: magic number, filesize, reserved, header final offset
        head_data = self.fp.read(14)
        # choke if the file does not have the required magic bytes
        if head_data[0:2] != b"BM":
            raise SyntaxError("Not a BMP file")
        # read the start position of the BMP image data (u32)
        offset = i32(head_data[10:14])
        # load bitmap information (offset=raster info)
        self._bitmap(offset=offset)


# ==============================================================================
# Image plugin for the DIB format (BMP alias)
# ==============================================================================
class DibImageFile(BmpImageFile):

    format = "DIB"
    format_description = "Windows Bitmap"

    def _open(self):
        self._bitmap()

#
# --------------------------------------------------------------------
# Write BMP file

SAVE = {
    "1": ("1", 1, 2),
    "L": ("L", 8, 256),
    "P": ("P", 8, 256),
    "RGB": ("BGR", 24, 0),
    "RGBA": ("BGRA", 32, 0),
}


def _save(im, fp, filename, check=0):
    try:
        rawmode, bits, colors = SAVE[im.mode]
    except KeyError:
        raise IOError("cannot write mode %s as BMP" % im.mode)

    if check:
        return check

    info = im.encoderinfo

    dpi = info.get("dpi", (96, 96))

    # 1 meter == 39.3701 inches
    ppm = tuple(map(lambda x: int(x * 39.3701), dpi))

    stride = ((im.size[0]*bits+7)//8+3) & (~3)
    header = 40  # or 64 for OS/2 version 2
    offset = 14 + header + colors * 4
    image = stride * im.size[1]

    # bitmap header
    fp.write(b"BM" +                      # file type (magic)
             o32(offset+image) +          # file size
             o32(0) +                     # reserved
             o32(offset))                 # image data offset

    # bitmap info header
    fp.write(o32(header) +                # info header size
             o32(im.size[0]) +            # width
             o32(im.size[1]) +            # height
             o16(1) +                     # planes
             o16(bits) +                  # depth
             o32(0) +                     # compression (0=uncompressed)
             o32(image) +                 # size of bitmap
             o32(ppm[0]) + o32(ppm[1]) +  # resolution
             o32(colors) +                # colors used
             o32(colors))                 # colors important

    fp.write(b"\0" * (header - 40))       # padding (for OS/2 format)

    if im.mode == "1":
        for i in (0, 255):
            fp.write(o8(i) * 4)
    elif im.mode == "L":
        for i in range(256):
            fp.write(o8(i) * 4)
    elif im.mode == "P":
        fp.write(im.im.getpalette("RGB", "BGRX"))

    ImageFile._save(im, fp, [("raw", (0, 0)+im.size, 0,
                    (rawmode, stride, -1))])

#
# --------------------------------------------------------------------
# Registry

Image.register_open(BmpImageFile.format, BmpImageFile, _accept)
Image.register_save(BmpImageFile.format, _save)

Image.register_extension(BmpImageFile.format, ".bmp")

Image.register_mime(BmpImageFile.format, "image/bmp")
