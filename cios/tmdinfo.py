import struct, sys
def parse_tmd(d):
    h = 0x140
    sysver, tid = struct.unpack('>QQ', d[h+0x44:h+0x54])
    access, tver, ncont, boot = struct.unpack('>IHHH', d[h+0x98:h+0xa2])
    cs = []
    for i in range(ncont):
        o = h + 0xa4 + 36*i
        cid, idx, typ, size = struct.unpack('>IHHQ', d[o:o+16])
        cs.append(dict(cid=cid, index=idx, type=typ, size=size, hash=d[o+16:o+36]))
    return dict(tid=tid, version=tver, boot=boot, contents=cs, sysver=sysver)
if __name__ == '__main__':
    t = parse_tmd(open(sys.argv[1], 'rb').read())
    print('tid %016x version %d boot %d contents %d' % (t['tid'], t['version'], t['boot'], len(t['contents'])))
    for c in t['contents']: print('  cid %02x idx %2d type %04x size %7d %s' % (c['cid'], c['index'], c['type'], c['size'], c['hash'].hex()[:12]))
