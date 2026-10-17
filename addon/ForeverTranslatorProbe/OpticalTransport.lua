local GRID_SIZE = 48
local SYMBOLS_PER_BYTE = 4
local BYTES_PER_ROW = GRID_SIZE / SYMBOLS_PER_BYTE
local SYNC_ROWS = 3
local FRAME_BYTES = GRID_SIZE * GRID_SIZE / SYMBOLS_PER_BYTE
local PACKET_BYTES = FRAME_BYTES - SYNC_ROWS * BYTES_PER_ROW
local HEADER_BYTES = 11
local CHECKSUM_BYTES = 2
local MAX_PACKET_PAYLOAD = PACKET_BYTES - HEADER_BYTES - CHECKSUM_BYTES
local CELL_SIZE = 2
local BORDER_CELLS = 1
local DWELL_SECONDS = 0.16
local HISTORY_LIMIT = 128
local MAX_MESSAGE_CHUNKS = 128
local MAX_QUEUE_PACKETS = 512
local HEARTBEAT_EVENT = "FT_HEARTBEAT"

local ATLAS_PATH = "Interface\\AddOns\\ForeverTranslatorProbe\\Textures\\QuadAtlas"

local syncBytes = string.rep(string.char(0x1B), BYTES_PER_ROW)
    .. string.rep(string.char(0xE4), BYTES_PER_ROW)
    .. string.rep(string.char(0x55, 0xAA), BYTES_PER_ROW / 2)

local state = {
    session = 0,
    sequence = 0,
    queue = {},
    queueHead = 1,
    queueTail = 0,
    history = {},
    historyIndex = 0,
    elapsed = 0,
    started = false,
}

local transportFrame
local gridFrame
local tiles = {}

local function u16(value)
    local low = value % 256
    local high = math.floor(value / 256) % 256
    return string.char(low, high)
end

local function fletcher16(value)
    local sum1 = 0
    local sum2 = 0
    for index = 1, #value do
        sum1 = (sum1 + string.byte(value, index)) % 255
        sum2 = (sum2 + sum1) % 255
    end
    return sum2 * 256 + sum1
end

local function encodePacket(sequence, chunkIndex, chunkCount, payload)
    local body = "FT"
        .. string.char(1)
        .. u16(state.session)
        .. u16(sequence)
        .. string.char(chunkIndex)
        .. string.char(chunkCount)
        .. u16(#payload)
        .. payload
    local packet = body .. u16(fletcher16(body))
    if #packet < PACKET_BYTES then
        packet = packet .. string.rep("\0", PACKET_BYTES - #packet)
    end
    return syncBytes .. packet
end

local function encodeMessage(event, author, text, playerClass)
    local safeEvent = tostring(event or "")
    local safeAuthor = tostring(author or "")
    local safeText = tostring(text or "")
    local safeClass = tostring(playerClass or "")
    if #safeEvent > 255 then
        safeEvent = string.sub(safeEvent, 1, 255)
    end
    if #safeAuthor > 255 then
        safeAuthor = string.sub(safeAuthor, 1, 255)
    end
    if #safeText > 65535 then
        safeText = string.sub(safeText, 1, 65535)
    end
    if #safeClass > 255 then
        safeClass = string.sub(safeClass, 1, 255)
    end
    return string.char(#safeEvent)
        .. string.char(#safeAuthor)
        .. u16(#safeText)
        .. safeEvent
        .. safeAuthor
        .. safeText
        .. string.char(#safeClass)
        .. safeClass
end

local function remember(packet)
    table.insert(state.history, packet)
    while #state.history > HISTORY_LIMIT do
        table.remove(state.history, 1)
    end
end

local function enqueuePacket(packet)
    state.queueTail = state.queueTail + 1
    state.queue[state.queueTail] = packet
end

local function enqueueMessage(event, message, author, playerClass)
    if not state.started then
        return
    end
    state.sequence = (state.sequence + 1) % 65536
    local payload = encodeMessage(event, author, message, playerClass)
    local chunkCount = math.max(1, math.ceil(#payload / MAX_PACKET_PAYLOAD))
    if chunkCount > MAX_MESSAGE_CHUNKS then
        return
    end
    local queued = math.max(0, state.queueTail - state.queueHead + 1)
    if queued + chunkCount > MAX_QUEUE_PACKETS then
        return
    end
    for chunkIndex = 0, chunkCount - 1 do
        local first = chunkIndex * MAX_PACKET_PAYLOAD + 1
        local chunk = string.sub(payload, first, first + MAX_PACKET_PAYLOAD - 1)
        enqueuePacket(encodePacket(state.sequence, chunkIndex, chunkCount, chunk))
    end
end

local function setTileByte(texture, value)
    local column = value % 16
    local row = math.floor(value / 16)
    texture:SetTexCoord(column / 16, (column + 1) / 16, row / 16, (row + 1) / 16)
end

local function render(packet)
    if not packet or #packet ~= FRAME_BYTES then
        return
    end
    for index = 1, FRAME_BYTES do
        setTileByte(tiles[index], string.byte(packet, index))
    end
    transportFrame:Show()
end

local function compactQueue()
    if state.queueHead > 64 and state.queueHead > (state.queueTail / 2) then
        local remaining = {}
        for index = state.queueHead, state.queueTail do
            table.insert(remaining, state.queue[index])
        end
        state.queue = remaining
        state.queueHead = 1
        state.queueTail = #remaining
    end
end

local function nextPacket()
    if state.queueHead <= state.queueTail then
        local packet = state.queue[state.queueHead]
        state.queueHead = state.queueHead + 1
        compactQueue()
        remember(packet)
        return packet
    end
    if #state.history == 0 then
        return nil
    end
    state.historyIndex = (state.historyIndex % #state.history) + 1
    return state.history[state.historyIndex]
end

local function initialize()
    if state.started then
        return
    end
    state.session = (time() + math.random(0, 65535)) % 65536

    local panelSize = (GRID_SIZE + BORDER_CELLS * 2) * CELL_SIZE
    transportFrame = CreateFrame("Frame", "ForeverTranslatorOpticalFrame", UIParent)
    transportFrame:SetSize(panelSize, panelSize)
    transportFrame:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 3, -3)
    transportFrame:SetFrameStrata("TOOLTIP")
    transportFrame:EnableMouse(false)

    local marker = transportFrame:CreateTexture(nil, "BACKGROUND")
    marker:SetAllPoints()
    marker:SetColorTexture(1, 0, 1, 1)

    gridFrame = CreateFrame("Frame", nil, transportFrame)
    gridFrame:SetPoint("TOPLEFT", transportFrame, "TOPLEFT", CELL_SIZE, -CELL_SIZE)
    gridFrame:SetSize(GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE)

    local background = gridFrame:CreateTexture(nil, "BACKGROUND")
    background:SetAllPoints()
    background:SetColorTexture(1, 1, 1, 1)

    local tileWidth = SYMBOLS_PER_BYTE * CELL_SIZE
    for row = 0, GRID_SIZE - 1 do
        for column = 0, BYTES_PER_ROW - 1 do
            local index = row * BYTES_PER_ROW + column + 1
            local tile = gridFrame:CreateTexture(nil, "ARTWORK")
            local textureOK = pcall(
                tile.SetTexture,
                tile,
                ATLAS_PATH,
                "CLAMP",
                "CLAMP",
                "NEAREST"
            )
            if not textureOK then
                tile:SetTexture(ATLAS_PATH)
            end
            tile:SetPoint("TOPLEFT", gridFrame, "TOPLEFT", column * tileWidth, -row * CELL_SIZE)
            tile:SetSize(tileWidth, CELL_SIZE)
            tiles[index] = tile
        end
    end

    -- A hidden frame does not receive OnUpdate in WoW. Render a valid control
    -- packet immediately so the calibration grid is visible and selectable
    -- before the first chat message arrives.
    local heartbeat = encodeMessage(HEARTBEAT_EVENT, "", "")
    render(encodePacket(0, 0, 1, heartbeat))

    transportFrame:SetScript("OnUpdate", function(_, elapsed)
        state.elapsed = state.elapsed + elapsed
        if state.elapsed < DWELL_SECONDS then
            return
        end
        state.elapsed = state.elapsed % DWELL_SECONDS
        render(nextPacket())
    end)
    state.started = true
end

ForeverTranslatorOptical = {
    Initialize = initialize,
    Enqueue = enqueueMessage,
    IsVisible = function()
        return transportFrame and transportFrame:IsShown() or false
    end,
}
