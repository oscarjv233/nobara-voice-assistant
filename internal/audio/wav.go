package audio

import (
	"encoding/binary"
	"io"
	"os"
)

// WriteWAVHeader writes a standard 44-byte RIFF WAV header for 16kHz mono S16LE.
func WriteWAVHeader(w io.Writer, dataSize uint32) error {
	totalChunkSize := 36 + dataSize
	sampleRate := uint32(16000)
	channels := uint16(1)
	bitsPerSample := uint16(16)
	byteRate := sampleRate * uint32(channels) * uint32(bitsPerSample/8)
	blockAlign := channels * (bitsPerSample / 8)

	header := make([]byte, 44)
	copy(header[0:4], []byte("RIFF"))
	binary.LittleEndian.PutUint32(header[4:8], totalChunkSize)
	copy(header[8:12], []byte("WAVE"))

	copy(header[12:16], []byte("fmt "))
	binary.LittleEndian.PutUint32(header[16:20], 16) // PCM subchunk size
	binary.LittleEndian.PutUint16(header[20:22], 1)  // Audio format 1 = PCM
	binary.LittleEndian.PutUint16(header[22:24], channels)
	binary.LittleEndian.PutUint32(header[24:28], sampleRate)
	binary.LittleEndian.PutUint32(header[28:32], byteRate)
	binary.LittleEndian.PutUint16(header[32:34], blockAlign)
	binary.LittleEndian.PutUint16(header[34:36], bitsPerSample)

	copy(header[36:40], []byte("data"))
	binary.LittleEndian.PutUint32(header[40:44], dataSize)

	_, err := w.Write(header)
	return err
}

// FinalizeWAV updates the RIFF and data chunk sizes in an existing WAV file.
func FinalizeWAV(f *os.File, dataSize uint32) error {
	if _, err := f.Seek(4, io.SeekStart); err != nil {
		return err
	}
	totalChunkSize := 36 + dataSize
	buf := make([]byte, 4)
	binary.LittleEndian.PutUint32(buf, totalChunkSize)
	if _, err := f.Write(buf); err != nil {
		return err
	}

	if _, err := f.Seek(40, io.SeekStart); err != nil {
		return err
	}
	binary.LittleEndian.PutUint32(buf, dataSize)
	_, err := f.Write(buf)
	return err
}
