meta.unsafe = true
require("os")

-- Keep in sync with PROTOCOL_VERSION in engine/protocol.py and __version__ in version.py
local PROTOCOL_VERSION = 1
local MOD_VERSION = "0.1.0"

------------- COMUNICATION ----------------
package.path = "lua/?.lua;" .. package.path
local socket = require("luasocket.socket")
local port = tonumber(os.getenv("Spelunky_RL_Port"))

local client = socket.tcp()
local success, err = client:connect("127.0.0.1", port)
if not success then
    error("Failed to connect: " .. tostring(err))
end
client:setoption("tcp-nodelay", true)  -- one small message each way per step: never wait to batch
client:send(json.encode({hello = {protocol = PROTOCOL_VERSION, mod = MOD_VERSION}}) .. "\n")

local pathfinding = require("spelunky2rl.pathfinding")
local observations = require("spelunky2rl.observations")


--------------- GLOBAL VARIABLES ----------------
local speedup = false
local manual_control = false
local state_updates = 0
local fast_forwarding = false  -- inside our own update_state() calls
local render_enabled = true
local data = {
    frames = 0,
    command = "pass"
}
local agent_input = nil  -- INPUTS applied every frame until the next step; nil = leave input alone

---------------- AUX FUNCTIONS ----------------
local function destroy_entities(entity_types)
    if #entity_types == 0 then
        return
    end
    for _, uid in ipairs(get_entities_by_type(entity_types)) do
        kill_entity(uid)
    end
end


set_post_entity_spawn(function(ent)
    ent:set_pre_destroy(pathfinding.mark_dirty)
    pathfinding.mark_dirty()
end, SPAWN_TYPE.ANY, MASK.FLOOR)

--------------- GAME CONTROL ----------------

-- Theme of the first level of each world. Worlds 2 and 4 also have an alternative
-- (Volcana, Temple) that can be requested explicitly with the `theme` reset option.
local world_themes = {
    THEME.DWELLING, THEME.JUNGLE, THEME.OLMEC, THEME.TIDE_POOL,
    THEME.ICE_CAVES, THEME.NEO_BABYLON, THEME.SUNKEN_CITY, THEME.COSMIC_OCEAN,
}

local function theme_for(world, level)
    if world == 6 and level == 4 then return THEME.TIAMAT end
    if world == 7 and level == 4 then return THEME.HUNDUN end
    return world_themes[world] or THEME.DWELLING
end

local function release_input()
    agent_input = nil
end

local function reset(seed, world, level, theme)
    state.quest_flags = 1
    set_adventure_seed(seed, seed)
    play_adventure()

    state.items.player_count = 1
    state.items.player_select[1].activated = true
    state.items.player_select[1].character = ENT_TYPE.CHAR_ANA_SPELUNKY

    warp(world, level, theme or theme_for(world, level))
end

local function set_start_values(restart_data)
    players[1].health = restart_data["hp"]
    players[1].inventory.bombs = restart_data["bombs"]
    players[1].inventory.ropes = restart_data["ropes"]
    players[1].inventory.money = restart_data["gold"]
end

local button_map = {
    BUTTON.JUMP,
    BUTTON.WHIP,
    BUTTON.BOMB,
    BUTTON.ROPE,
    BUTTON.RUN,
    BUTTON.DOOR,
}

local function booleans_to_button_mask(booleans)
    local mask = 0
    for i, pressed in ipairs(booleans) do
        if pressed == 1 then
            mask = mask | button_map[i]
        end
    end
    return mask
end


set_callback(function()

    -- DISABLE PAUSE
    local level_flags = get_level_flags()
    level_flags = level_flags & ~(1 << 19)
    set_level_flags(level_flags)

    data["frames"] = data["frames"] - 1
    if data["frames"] <= 0 then

        -- SEND
        if data["command"] == "step" then
            local serialized_data = json.encode(observations.collect(data["data_to_send"]))
            client:send(serialized_data .. "\n")

        elseif data["command"] == "reset" then
            -- LOAD ITEMS, etc
            destroy_entities(data["ent_types_to_destroy"])
            set_start_values(data)
            local serialized_data = json.encode(observations.collect(data["data_to_send"]))
            client:send(serialized_data .. "\n")
        end

        -- RECEIVE
        local line, err = client:receive("*l")
        if not line then
            -- Python side is gone: nothing will ever drive this instance again
            print("spelunky2rl: connection lost (" .. tostring(err) .. "), exiting")
            os.exit()
        end
        data = json.decode(line)

        if data["command"] == "reset" then
            release_input()
            reset(data["seed"], data["world"], data["level"], data["theme"])
            data["frames"] = 60

            -- INITIAL SETTINGS
            speedup = data["speedup"]
            state_updates = data["state_updates"]
            set_speedhack(speedup and 100 or 1)
            if data["vsync"] ~= nil then set_setting(GAME_SETTING.VSYNC, data["vsync"] and 1 or 0) end
            if data["audio"] ~= nil then set_setting(GAME_SETTING.MASTER_ENABLED, data["audio"] and 1 or 0) end
            if data["time_ghost"] ~= nil then set_time_ghost_enabled(data["time_ghost"]) end
            if data["render"] ~= nil then
                render_enabled = data["render"]
            end
            manual_control = data["manual_control"]
            if data["god_mode"] then
                god(true)
            else
                god(false)
            end

        elseif data["command"] == "step" and #players ~= 0 then
            local python_input = data["input"]
            local last6 = {}
            table.move(python_input, #python_input - 5, #python_input, 1, last6)
            local buttons = booleans_to_button_mask(last6)

            if not manual_control then
                -- x, y go from -1 to 1
                agent_input = buttons_to_inputs(python_input[1]-1, python_input[2]-1, buttons) -- arrays in lua start at 1
            end

        elseif data["command"] == "close" then
            release_input()
            set_speedhack(1)
            os.exit()
        end

    end 
    -- Speedup: simulate state_updates extra logic frames per rendered frame. update_state() fires
    -- POST_UPDATE again (this same callback, which also runs the protocol above); the flag keeps
    -- those nested calls from starting their own loop, which used to recurse state_updates deep.
    if speedup and not fast_forwarding then
        fast_forwarding = true
        for _ = 1, state_updates do
            update_state()
        end
        fast_forwarding = false
    end
end, ON.POST_UPDATE)

set_callback(observations.on_transition, ON.TRANSITION)

-- Headless: skip drawing the level and the HUD when nobody looks at the frames
set_callback(function()
    if not render_enabled then return true end
end, ON.RENDER_PRE_GAME)

set_callback(function()
    if not render_enabled then return true end
end, ON.RENDER_PRE_HUD)

-- The agent's input, written before every logic frame (also the ones run by update_state()).
-- steal_input/send_input used to do this, but overlunky deprecates them as crash-prone, and the
-- input was silently ignored in ~40% of episodes (the player never moved).
set_callback(function()
    if agent_input ~= nil and not manual_control then
        state.player_inputs.player_slot_1.buttons_gameplay = agent_input
        state.player_inputs.player_slot_1.buttons = agent_input
    end
end, ON.PRE_UPDATE)
