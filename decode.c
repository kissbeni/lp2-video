#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>

typedef struct _crle_decode_s {
    bool header_received;
    uint8_t top_codes[2];
    float frame_time;
    uint8_t state;
    uint32_t consecutive_zeros;
    uint16_t pos;
    uint8_t prev_byte;
    uint8_t rare_byte_pos;
    bool in_frame;
    uint8_t frame_buffer[(32*24)/8];
} crle_decode_t;

enum {
    CRLE_WAIT_SYMBOL = 0,
    CRLE_RARE_BYTE = 1,
};

void crle_frame_start(crle_decode_t* est) {
    est->state = CRLE_WAIT_SYMBOL;
    est->consecutive_zeros = 0;
    est->prev_byte = 0;
    est->pos = 0;
    est->in_frame = true;
    memset(est->frame_buffer, 0, 32*24/8);
}

void crle_on_frame(crle_decode_t* est) {
    for (int i = 0; i < (32*24/8); ++i) {
        printf("%02x", est->frame_buffer[i]);
    }
    for (int i = 0; i < 32*24; ++i) {
        if ((i%32)==0) printf("\n");
        if (est->frame_buffer[i/8] & (1<<(i%8)))
            printf("##");
        else
            printf("..");
    }
    printf("\n");
    // usleep(est->frame_time * 1000);
}

void clre_feed_line(crle_decode_t* est, bool color, uint8_t len) {
    // printf("line %d %d\n", color, len);
    for (int i = 0; i < len; ++i) {
        if (est->pos == 32*24) {
            printf("overrun!\n"); // last lines of frames will often overrun to fill the entire frame; this is normal to see
            return;
        }
        if (color) est->frame_buffer[est->pos/8] |= (1<<(est->pos%8));
        if (++est->pos == 32*24) {
            crle_on_frame(est);
            // printf("frame end!\n");
        }
    }
}

void crle_feed_run_pair(crle_decode_t* est, uint8_t b) {
    est->prev_byte = b;
    clre_feed_line(est, !!(b&0x80), ((b>>4)&7)+2);
    clre_feed_line(est, !!(b&0x08), (b&7)+2);
}

void crle_feed_byte(crle_decode_t* est, uint8_t b) {
    bool cont = false;
    uint8_t bitpos = 0;
    do {
        // printf("bitpos on start of cycle: %d %d\n", bitpos, est->consecutive_zeros);
        switch (est->state) {
            case CRLE_WAIT_SYMBOL:
                // count zeros until a one; a frame start is at least 4 zeros followed by a one
                for (; bitpos < 8; ++bitpos) {
                    if (((b << bitpos) & 0x80)) {
                        if (est->in_frame) {
                            // code for most comoon byte
                            if (est->consecutive_zeros == 0) {
                                ++bitpos;
                                crle_feed_run_pair(est, est->top_codes[0]);
                                break;
                            }
                            // code for second most common byte
                            if (est->consecutive_zeros == 1) {
                                ++bitpos;
                                crle_feed_run_pair(est, est->top_codes[1]);
                                est->consecutive_zeros = 0;
                                break;
                            }
                            // code for repeated byte
                            if (est->consecutive_zeros == 2) {
                                ++bitpos;
                                crle_feed_run_pair(est, est->prev_byte);
                                est->consecutive_zeros = 0;
                                break;
                            }
                            // code for rare byte
                            if (est->consecutive_zeros == 3) {
                                ++bitpos;
                                est->prev_byte = 0;
                                est->rare_byte_pos = 0;
                                est->consecutive_zeros = 0;
                                est->state = CRLE_RARE_BYTE;
                                break;
                            }
                        }
                        if (est->consecutive_zeros >= 4) {
                            ++bitpos;
                            crle_frame_start(est);
                            break;
                        }
                    } else ++est->consecutive_zeros;
                }
                break;
            case CRLE_RARE_BYTE:
                for (; bitpos < 8; ++bitpos) {
                    est->prev_byte <<= 1;
                    est->prev_byte |= !!((b << bitpos) & 0x80);
                    // printf("decode byte: %02x %d %d\n", est->prev_byte, bitpos, !!((b << bitpos) & 0x80));
                    if (++est->rare_byte_pos == 8) {
                        crle_feed_run_pair(est, est->prev_byte);
                        est->state = CRLE_WAIT_SYMBOL;
                        ++bitpos;
                        break;
                    }
                }
                break;
            default:
                abort();
        }
    } while(bitpos < 8);
}

int main() {
    FILE* fp = fopen("local/ba.mdslot", "rb");
    // FILE* fp = fopen("local/ba_dump.mdslot", "rb");
    fseek(fp, 14, SEEK_SET);

    uint8_t slot[0x920];
    uint8_t buffer[8*11];

    crle_decode_t est;
    memset(&est, 0, sizeof(est));

    for (;;) {
        if (fread(slot, 0x920, 1, fp) != 1)
            break;

        for (int i = 0; i < 11; ++i) {
            memcpy(&buffer[i*8], &slot[208+(212*i)], 8);
        }

        for (int i = 0; i < 8*11; i++) {
            if (!est.header_received) {
                if (i % 8 == 0 && buffer[i] == 0xA5 && buffer[i+1] == 0x02) {
                    est.top_codes[0] = buffer[i+2];
                    est.top_codes[1] = buffer[i+3];
                    uint16_t time_dms = ((uint16_t)buffer[i+4])<<8 | buffer[i+5];
                    est.frame_time = time_dms / 10.0f;
                    printf("Got header: %02x %02x; frametime=%.1fms\n", est.top_codes[0], est.top_codes[1], est.frame_time);
                    i += 5;
                    est.header_received = true;
                }
                continue;
            }
            // printf("%02x ", buffer[i]);
            crle_feed_byte(&est, buffer[i]);
        }
        // printf("\n");
    }
    end:

    fclose(fp);
    return 0;
}
