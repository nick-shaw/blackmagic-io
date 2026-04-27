#pragma once

#include "decklink_common.hpp"
#include <memory>
#include <vector>
#include <atomic>
#include <mutex>
#include <condition_variable>
#include <string>

class DeckLinkInputCallback;

class DeckLinkInput {
public:
    using PixelFormat = DeckLink::PixelFormat;
    using DisplayMode = DeckLink::DisplayMode;
    using Gamut = DeckLink::Gamut;
    using Eotf = DeckLink::Eotf;
    using VideoSettings = DeckLink::VideoSettings;
    using DisplayModeInfo = DeckLink::DisplayModeInfo;
    using InputConnection = DeckLink::InputConnection;

    struct CapturedFrame {
        std::vector<uint8_t> data;
        int width;
        int height;
        int rowBytes;
        PixelFormat format;
        DisplayMode mode;
        Gamut colorspace;
        Eotf eotf;
        bool hasMetadata;
        bool valid;

        double displayPrimariesRedX;
        double displayPrimariesRedY;
        double displayPrimariesGreenX;
        double displayPrimariesGreenY;
        double displayPrimariesBlueX;
        double displayPrimariesBlueY;
        bool hasDisplayPrimaries;

        double whitePointX;
        double whitePointY;
        bool hasWhitePoint;

        double maxMasteringLuminance;
        double minMasteringLuminance;
        bool hasMasteringLuminance;

        double maxContentLightLevel;
        bool hasMaxCLL;

        double maxFrameAverageLightLevel;
        bool hasMaxFALL;

        bool hasTimecode;
        uint8_t timecodeHours;
        uint8_t timecodeMinutes;
        uint8_t timecodeSeconds;
        uint8_t timecodeFrames;
        bool timecodeIsDropFrame;
    };

    DeckLinkInput();
    ~DeckLinkInput();

    bool initialize(int deviceIndex = 0, InputConnection* inputConnection = nullptr);
    bool startCapture(PixelFormat format = PixelFormat::Format10BitYUV);
    bool captureFrame(CapturedFrame& frame, int timeoutMs = 5000);
    bool stopCapture();
    void cleanup();

    // Set the BMDDynamicRange bitmask advertised in the HDMI input EDID so
    // sources know which transfer functions they may transmit. Default is
    // bmdDynamicRangeSDR | bmdDynamicRangeHDRStaticPQ | bmdDynamicRangeHDRStaticHLG.
    // Pass any combination of BMDDynamicRange bits as an int64_t. May be called
    // before or after initialize(); if called before, the mask is applied at
    // initialize() time. Has no effect on non-HDMI connections or on hardware
    // that does not expose IDeckLinkHDMIInputEDID. The library releases its
    // reference on cleanup, which restores the EDID to its default per the SDK.
    bool setHDMIInputDynamicRanges(int64_t bmdDynamicRangeMask);

    VideoSettings getDetectedFormat();
    PixelFormat getDetectedPixelFormat();

    std::vector<std::string> getDeviceList();
    std::vector<InputConnection> getAvailableInputConnections(int deviceIndex = 0);
    VideoSettings getVideoSettings(DisplayMode mode);
    std::vector<DisplayModeInfo> getSupportedDisplayModes();

private:
    friend class DeckLinkInputCallback;

    IDeckLink* m_deckLink;
    IDeckLinkInput* m_deckLinkInput;
    IDeckLinkConfiguration* m_deckLinkConfiguration;
    IDeckLinkHDMIInputEDID* m_hdmiInputEDID;
    DeckLinkInputCallback* m_callback;

    int64_t m_hdmiInputDynamicRanges;

    bool applyHDMIInputDynamicRanges();

    VideoSettings m_currentSettings;
    std::atomic<bool> m_inputEnabled;

    std::mutex m_frameMutex;
    std::condition_variable m_frameCondition;
    CapturedFrame m_lastFrame;
    std::atomic<bool> m_frameReceived;

    std::mutex m_formatMutex;
    std::atomic<bool> m_formatDetected;
    VideoSettings m_detectedSettings;

    void onFrameArrived(IDeckLinkVideoInputFrame* videoFrame);
    void onFormatChanged(IDeckLinkDisplayMode* newDisplayMode, BMDDetectedVideoInputFormatFlags detectedSignalFlags);
};
