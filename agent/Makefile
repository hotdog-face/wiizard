# wii-agent: build with   docker run --rm -v "$PWD":/src -w /src devkitpro/devkitppc make
.SUFFIXES:
ifeq ($(strip $(DEVKITPPC)),)
$(error "Please set DEVKITPPC in your environment. export DEVKITPPC=<path to>devkitPPC")
endif
include $(DEVKITPPC)/wii_rules

TARGET   := wii-agent
BUILD    := build
SOURCES  := source lwip/core lwip/core/ipv4 lwip/api lwip/netif
INCLUDES := source/lwipport lwip/include

CFLAGS   = -g -O2 -Wall $(MACHDEP) $(INCLUDE) -D_REENTRANT -I$(DEVKITPRO)/portlibs/ppc/include/freetype2
LDFLAGS  = -g $(MACHDEP) -Wl,-Map,$(notdir $@).map
LIBS     := -lasnd -lturbojpeg -lSDL2_ttf -lharfbuzz -lfreetype -lbz2 -lbrotlidec -lbrotlicommon -lSDL2_image -lpng16 -ljpeg -lz -lSDL2 -lfat -ldi -lwiiuse -lbte -logc -lm
LIBDIRS  := $(DEVKITPRO)/portlibs/wii $(DEVKITPRO)/portlibs/ppc

ifneq ($(BUILD),$(notdir $(CURDIR)))
export OUTPUT   := $(CURDIR)/$(TARGET)
export VPATH    := $(foreach dir,$(SOURCES),$(CURDIR)/$(dir))
export DEPSDIR  := $(CURDIR)/$(BUILD)
CFILES          := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.c)))
SFILES          := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.s)))
export LD       := $(CC)
export OFILES   := $(CFILES:.c=.o) $(SFILES:.s=.o)
export INCLUDE  := $(foreach dir,$(INCLUDES),-I$(CURDIR)/$(dir)) $(foreach dir,$(LIBDIRS),-I$(dir)/include) -I$(CURDIR)/$(BUILD) -I$(LIBOGC_INC)
export LIBPATHS := $(foreach dir,$(LIBDIRS),-L$(dir)/lib) -L$(LIBOGC_LIB)
.PHONY: $(BUILD) clean
$(BUILD):
	@[ -d $@ ] || mkdir -p $@
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile
clean:
	@rm -fr $(BUILD) $(OUTPUT).elf $(OUTPUT).dol
else
$(OUTPUT).dol: $(OUTPUT).elf
$(OUTPUT).elf: $(OFILES)
-include $(DEPSDIR)/*.d
endif
