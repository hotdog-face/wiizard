// disc: the Wii's disc drive from the launcher, through libogc's libdi (with AHBPROT it drives the DI hardware
// directly: no cIOS, no DVDX). Phase 1 of the disc work: what drive is this, can it read DVDs, what disc is in it.
#ifndef DISC_H
#define DISC_H

// Agent command DISC:
//   DISC INFO                        drive id (rev, device code, firmware date), DVD-capable verdict, cover, and for an
//                                    inserted disc: read mode (D0/A8), GameCube/Wii id + title, or the ISO9660 volume id
//   DISC READ <lba> <count> <file>   raw 2048-byte sectors to a file on the card (count <= 4096)
//   DISC CLOSE                       stop the motor and let go of the drive (before a game uses it)
// Writes one result line to out ("OK ..." or "ERR ...").
void disc_command(const char *arg, char *out, int size);

#endif
