# Boot stub for EXEC. main.c copies these instructions to the top of MEM2 (outside anything a program loads into)
# and calls them with interrupts off:
#   r3 = copy list: u32 count, then count x { u32 dst, u32 src (0 = fill with zeros), u32 len }
#   r4 = entry point
# Position independent: only relative branches, no data references. Copies every range, flushes it from the data
# cache and invalidates the instruction cache, then jumps to the entry point.
	.section .rodata
	.globl booter_start, booter_end
	.balign 32
booter_start:
	lwz	5, 0(3)
	addi	3, 3, 4
next_range:
	cmpwi	5, 0
	beq	go
	lwz	6, 0(3)		# dst
	lwz	7, 4(3)		# src
	lwz	8, 8(3)		# len
	addi	3, 3, 12
	mr	9, 6
	mr	11, 8
copy:
	cmpwi	11, 0
	beq	flush
	li	10, 0
	cmpwi	7, 0
	beq	store
	lbz	10, 0(7)
	addi	7, 7, 1
store:
	stb	10, 0(9)
	addi	9, 9, 1
	subi	11, 11, 1
	b	copy
flush:
	rlwinm	9, 6, 0, 0, 26	# start, rounded down to a 32-byte cache line
	add	10, 6, 8		# end
flush_line:
	cmplw	9, 10
	bge	range_done
	dcbst	0, 9
	sync
	icbi	0, 9
	addi	9, 9, 32
	b	flush_line
range_done:
	subi	5, 5, 1
	b	next_range
go:
	sync
	isync
	mtctr	4
	bctr
	.balign 32
booter_end:
