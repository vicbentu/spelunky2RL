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
local control = require("spelunky2rl.control")
local input = require("spelunky2rl.input")


--------------- GLOBAL VARIABLES ----------------
local speedup = false
local state_updates = 0
local fast_forwarding = false  -- inside our own update_state() calls
local data = {
    frames = 0,
    command = "pass"
}

set_post_entity_spawn(function(ent)
    ent:set_pre_destroy(pathfinding.mark_dirty)
    pathfinding.mark_dirty()
end, SPAWN_TYPE.ANY, MASK.FLOOR)

set_callback(function()

    control.disable_pause()

    data["frames"] = data["frames"] - 1
    if data["frames"] <= 0 then

        -- SEND
        if data["command"] == "step" then
            local serialized_data = json.encode(observations.collect(data["data_to_send"]))
            client:send(serialized_data .. "\n")

        elseif data["command"] == "reset" then
            -- LOAD ITEMS, etc
            control.destroy_entities(data["ent_types_to_destroy"])
            control.set_start_values(data)
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
            input.release()
            control.start_level(data["seed"], data["world"], data["level"], data["theme"])
            data["frames"] = 60

            speedup = data["speedup"]
            state_updates = data["state_updates"]
            control.apply_options(data)
            input.set_manual_control(data["manual_control"])

        elseif data["command"] == "step" and #players ~= 0 then
            input.hold(data["input"])

        elseif data["command"] == "close" then
            input.release()
            control.set_speedup(false)
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

set_callback(control.skip_render, ON.RENDER_PRE_GAME)
set_callback(control.skip_render, ON.RENDER_PRE_HUD)
set_callback(input.apply, ON.PRE_UPDATE)
