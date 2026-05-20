#pragma once

#include "decklink_common.hpp"
#include <memory>
#include <functional>
#include <vector>
#include <thread>
#include <atomic>
#include <mutex>
#include <string>

class DeckLinkOutput {
public:
    using PixelFormat = DeckLink::PixelFormat;
    using DisplayMode = DeckLink::DisplayMode;
    using Matrix = DeckLink::Matrix;
    using Gamut = DeckLink::Gamut;
    using Eotf = DeckLink::Eotf;
    using VideoSettings = DeckLink::VideoSettings;
    using DisplayModeInfo = DeckLink::DisplayModeInfo;

    struct HdrStaticMetadata {
        double displayPrimariesRedX = 0.64;
        double displayPrimariesRedY = 0.33;
        double displayPrimariesGreenX = 0.30;
        double displayPrimariesGreenY = 0.60;
        double displayPrimariesBlueX = 0.15;
        double displayPrimariesBlueY = 0.06;
        double whitePointX = 0.3127;
        double whitePointY = 0.3290;
        double maxMasteringLuminance = 1000.0;
        double minMasteringLuminance = 0.0001;
        double maxContentLightLevel = 1000.0;
        double maxFrameAverageLightLevel = 50.0;
    };

    struct OutputInfo {
        DisplayMode displayMode;
        PixelFormat pixelFormat;
        int width;
        int height;
        double framerate;
        bool rgb444ModeEnabled;
        std::string displayModeName;
        std::string pixelFormatName;
    };

    DeckLinkOutput();
    ~DeckLinkOutput();

    bool initialize(int deviceIndex = 0);
    bool setupOutput(const VideoSettings& settings);
    bool setFrameData(const uint8_t* data, size_t dataSize);
    bool displayFrame();
    bool stopOutput();
    void cleanup();

    std::vector<std::string> getDeviceList();
    VideoSettings getVideoSettings(DisplayMode mode);
    bool isPixelFormatSupported(DisplayMode mode, PixelFormat format);

    // Per-field signal-metadata setters. The matrix names the Y'CbCr coefficient
    // set (Rec.601/709/2020) used for YUV encoding and signalled on the wire
    // (VPID for SDI, AVI InfoFrame for HDMI). The EOTF identifies the transfer
    // function; setting it to non-SDR triggers HDR Static Metadata InfoFrame
    // transmission on the next emitted frame. setStaticMetadata overrides the
    // primaries / white point / mastering-luminance defaults that setMatrix
    // fills based on the matrix name; only meaningful for PQ output (the SDK
    // zeroes the InfoFrame for HLG and SDR).
    //
    // HDMI note: BMD's HDMI driver caches the HDR Static Metadata InfoFrame, so
    // a subsequent displayFrame() call is required for HDMI consumers to see
    // updated values mid-stream. SDI carries metadata per-frame and updates on
    // the next frame without any extra step.
    void setMatrix(Matrix matrix);
    void setEotf(Eotf eotf);
    void setStaticMetadata(const HdrStaticMetadata& staticMetadata);
    OutputInfo getCurrentOutputInfo();
    std::vector<DisplayModeInfo> getSupportedDisplayModes();

private:
    IDeckLink* m_deckLink;
    IDeckLinkOutput* m_deckLinkOutput;
    IDeckLinkConfiguration* m_deckLinkConfiguration;

    VideoSettings m_currentSettings;
    std::vector<uint8_t> m_frameBuffer;
    std::mutex m_frameBufferMutex;
    std::atomic<bool> m_outputEnabled;

    BMDTimeValue m_frameDuration;
    BMDTimeScale m_timeScale;

    bool m_signalMetadata;
    Matrix m_matrix;
    Eotf m_hdrEotf;
    HdrStaticMetadata m_hdrStaticMetadata;

    bool createFrame(IDeckLinkMutableVideoFrame** frame);
    IDeckLinkVideoFrame* createHdrFrame(IDeckLinkMutableVideoFrame* frame);
};
