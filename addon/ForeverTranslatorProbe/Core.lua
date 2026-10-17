local ADDON_NAME = ...

local CHAT_EVENTS = {
    "CHAT_MSG_SAY",
    "CHAT_MSG_YELL",
    "CHAT_MSG_WHISPER",
    "CHAT_MSG_WHISPER_INFORM",
    "CHAT_MSG_PARTY",
    "CHAT_MSG_PARTY_LEADER",
    "CHAT_MSG_RAID",
    "CHAT_MSG_RAID_LEADER",
    "CHAT_MSG_RAID_WARNING",
    "CHAT_MSG_GUILD",
    "CHAT_MSG_OFFICER",
    "CHAT_MSG_INSTANCE_CHAT",
    "CHAT_MSG_INSTANCE_CHAT_LEADER",
    "CHAT_MSG_CHANNEL",
    "CHAT_MSG_EMOTE",
    "CHAT_MSG_SYSTEM",
}

local state = {
    counts = {},
    unsupported = {},
    recent = {},
    logging = "UNVERIFIED",
    apiVerified = false,
}

local eventFrame = CreateFrame("Frame")
local panel
local statusText
local countText
local recentText

local function shortEvent(event)
    return string.gsub(event, "CHAT_MSG_", "")
end

local function refreshPanel()
    if not panel then
        return
    end

    local unsupportedCount = 0
    for _ in pairs(state.unsupported) do
        unsupportedCount = unsupportedCount + 1
    end
    local apiState = state.apiVerified and "VERIFIED" or "UNVERIFIED"
    local opticalState = "OFF"
    if ForeverTranslatorOptical and ForeverTranslatorOptical.IsVisible then
        opticalState = ForeverTranslatorOptical.IsVisible() and "ON" or "OFF"
    end
    statusText:SetText(
        "Chat log: " .. state.logging
        .. "   |   beta API: " .. apiState
        .. "   |   optical: " .. opticalState
        .. "   |   nepodporované eventy: " .. unsupportedCount
    )

    local countLines = {}
    for _, event in ipairs(CHAT_EVENTS) do
        local value = state.counts[event] or 0
        if value > 0 then
            table.insert(countLines, shortEvent(event) .. ": " .. value)
        end
    end
    if #countLines == 0 then
        table.insert(countLines, "Čekám na první CHAT_MSG_* událost…")
    end
    countText:SetText(table.concat(countLines, "   "))
    recentText:SetText(table.concat(state.recent, "\n"))
end

local function setLoggingState()
    if type(LoggingChat) ~= "function" then
        state.logging = "UNAVAILABLE"
        return
    end

    local ok, result = pcall(LoggingChat, true)
    if not ok then
        state.logging = "UNVERIFIED"
        return
    end

    if result == true then
        state.logging = "ON"
    elseif result == false then
        state.logging = "OFF"
    else
        local checkOK, current = pcall(LoggingChat)
        state.logging = checkOK and current and "ON" or "UNVERIFIED"
    end
end

local function createPanel()
    panel = CreateFrame("Frame", "ForeverTranslatorProbePanel", UIParent)
    panel:SetSize(560, 245)
    panel:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 30, -120)
    panel:SetMovable(true)
    panel:EnableMouse(true)
    panel:RegisterForDrag("LeftButton")
    panel:SetScript("OnDragStart", panel.StartMoving)
    panel:SetScript("OnDragStop", function(self)
        self:StopMovingOrSizing()
        local point, _, relativePoint, x, y = self:GetPoint()
        ForeverTranslatorProbeDB.position = { point, relativePoint, x, y }
    end)

    local background = panel:CreateTexture(nil, "BACKGROUND")
    background:SetAllPoints()
    background:SetColorTexture(0.02, 0.02, 0.02, 0.84)

    local title = panel:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    title:SetPoint("TOPLEFT", 12, -10)
    title:SetText("Forever Translator")

    statusText = panel:CreateFontString(nil, "OVERLAY", "ChatFontNormal")
    statusText:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -10)

    countText = panel:CreateFontString(nil, "OVERLAY", "ChatFontNormal")
    countText:SetPoint("TOPLEFT", statusText, "BOTTOMLEFT", 0, -12)
    countText:SetPoint("RIGHT", panel, "RIGHT", -12, 0)
    countText:SetJustifyH("LEFT")
    countText:SetWordWrap(true)

    recentText = panel:CreateFontString(nil, "OVERLAY", "ChatFontNormal")
    recentText:SetPoint("TOPLEFT", countText, "BOTTOMLEFT", 0, -16)
    recentText:SetPoint("RIGHT", panel, "RIGHT", -12, 0)
    recentText:SetJustifyH("LEFT")
    recentText:SetWordWrap(true)

    if ForeverTranslatorProbeDB.position then
        local p = ForeverTranslatorProbeDB.position
        panel:ClearAllPoints()
        panel:SetPoint(p[1], UIParent, p[2], p[3], p[4])
    end
end

local function classFromGUID(guid)
    if not guid or guid == "" or type(GetPlayerInfoByGUID) ~= "function" then
        return ""
    end
    local ok, _, classToken = pcall(GetPlayerInfoByGUID, guid)
    if ok and classToken then
        return tostring(classToken)
    end
    return ""
end

local function capture(event, message, author, ...)
    state.apiVerified = true
    state.counts[event] = (state.counts[event] or 0) + 1
    local safeMessage = tostring(message or "")
    local safeAuthor = tostring(author or "")
    local guid = select(10, ...)
    local classToken = classFromGUID(guid)
    local line = string.format("[%s] %s: %s", shortEvent(event), safeAuthor, safeMessage)
    table.insert(state.recent, 1, line)
    while #state.recent > 6 do
        table.remove(state.recent)
    end

    ForeverTranslatorProbeDB.counts = state.counts
    ForeverTranslatorProbeDB.lastEvent = {
        event = event,
        capturedAt = date("!%Y-%m-%dT%H:%M:%SZ"),
    }
    if ForeverTranslatorOptical then
        ForeverTranslatorOptical.Enqueue(event, safeMessage, safeAuthor, classToken)
    end
    refreshPanel()
end

eventFrame:SetScript("OnEvent", function(_, event, ...)
    if event == "ADDON_LOADED" then
        local loadedName = ...
        if loadedName ~= ADDON_NAME then
            return
        end

        ForeverTranslatorProbeDB = ForeverTranslatorProbeDB or {}
        state.counts = ForeverTranslatorProbeDB.counts or {}
        state.apiVerified = next(state.counts) ~= nil
        setLoggingState()
        if ForeverTranslatorOptical then
            ForeverTranslatorOptical.Initialize()
        end

        for _, chatEvent in ipairs(CHAT_EVENTS) do
            local ok = pcall(eventFrame.RegisterEvent, eventFrame, chatEvent)
            if not ok then
                state.unsupported[chatEvent] = true
            end
        end
        refreshPanel()
    elseif string.sub(event, 1, 9) == "CHAT_MSG_" then
        capture(event, ...)
    end
end)

eventFrame:RegisterEvent("ADDON_LOADED")

SLASH_FOREVERTRANSLATORPROBE1 = "/ftp"
SlashCmdList.FOREVERTRANSLATORPROBE = function()
    if not panel then
        createPanel()
        refreshPanel()
        return
    end
    if panel:IsShown() then
        panel:Hide()
    else
        panel:Show()
    end
end

