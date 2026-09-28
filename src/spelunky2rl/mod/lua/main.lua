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


--------------- GLOBAL VARIABLES ----------------
local transition = 0
local speedup = false
local manual_control = false
local state_updates = 0
local fast_forwarding = false  -- inside our own update_state() calls
local render_enabled = true
local data = {
    frames = 0,
    command = "pass"
}
local tiles = nil
local stolen_input_uid = nil

local x, y, vel_x, vel_y, health, money, bombs, ropes, layer, map_info, face_left_player, holding_type_player, back_item, dist_to_goal, pos_type_matrix, char_state, can_jump = 
      0, 0, 0,     0,     0,      0,     0,     0,     0,     0,        0,                 0,                  0,         0,            0,               0,          false
local powerups = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0} -- 18 powerups, 0 = not, 1 = yes

---------------- PATHFINDING ----------------
local Grid        = require ("jumper.grid")
local Pathfinder  = require ("jumper.pathfinder")

local pf_grid       = nil        -- jumper grid
local pf_finder     = nil        -- jumper finder
local pf_board      = {}         -- 0 = walkable, 1 = blocked
local pf_ntiles     = 0          -- rebuild only if the number of floor tiles changes
local pf_xmin, pf_ymin, pf_xmax, pf_ymax = 0,0,0,0
local pf_goalx, pf_goaly = 0,0   -- exit cell coords
local pf_dirty = true
local last_distance = -1
local pf_dist = {}
local pf_tile_lookup = {}


---------------- AUX FUNCTIONS ----------------
local function safe(val, default)
    if val ~= nil and val then
        return val
    else
        return default
    end
end

function math.round(x)
    return math.floor(x + 0.5)
end

function destroy_entities(entity_types)
    if #entity_types == 0 then
        return
    end
    for _, uid in ipairs(get_entities_by_type(entity_types)) do
        kill_entity(uid)
    end
end


local function pf_build_distance_field()
    pf_dist = {}
    for y = 1, #pf_board do
        pf_dist[y] = {}
        for x = 1, #pf_board[1] do
            pf_dist[y][x] = -1
        end
    end

    local qx, qy = {}, {}
    local qh, qt = 1, 1

    local function enqueue(x, y, d)
        qx[qt], qy[qt] = x, y
        pf_dist[y][x]  = d
        qt = qt + 1
    end

    enqueue(pf_goalx, pf_goaly, 0)

    while qh < qt do
        local x, y   = qx[qh], qy[qh]
        local d_next = pf_dist[y][x] + 1
        qh = qh + 1

        if y > 1               and pf_board[y-1][x] == 0 and pf_dist[y-1][x] < 0 then enqueue(x,   y-1, d_next) end
        if y < #pf_board       and pf_board[y+1][x] == 0 and pf_dist[y+1][x] < 0 then enqueue(x,   y+1, d_next) end
        if x > 1               and pf_board[y][x-1] == 0 and pf_dist[y][x-1] < 0 then enqueue(x-1, y,   d_next) end
        if x < #pf_board[1]    and pf_board[y][x+1] == 0 and pf_dist[y][x+1] < 0 then enqueue(x+1, y,   d_next) end
    end
end


local function pf_refresh()
    local tiles = get_entities_by(0, MASK.FLOOR, 0)
    if #tiles == pf_ntiles then return end
    pf_ntiles = #tiles

    pf_tile_lookup = {}
    local xmin, xmax =  math.huge, -math.huge
    local ymin, ymax = -math.huge,  math.huge

    local blocking = {}

    for _, uid in ipairs(tiles) do
        local e        = get_entity(uid)
        local tx,  ty  = math.floor(e.x), math.floor(e.y)
        local layer    = e.layer

        pf_tile_lookup[layer]           = pf_tile_lookup[layer]           or {}
        pf_tile_lookup[layer][ty]       = pf_tile_lookup[layer][ty]       or {}
        pf_tile_lookup[layer][ty][tx]   = e.type.id

        if tx < xmin then xmin = tx end
        if tx > xmax then xmax = tx end
        if ty > ymin then ymin = ty end
        if ty < ymax then ymax = ty end

        if (test_flag(e.flags, 3) and e.type.id ~= ENT_TYPE.FLOOR_PIPE)
           or e.type.id == ENT_TYPE.FLOOR_SPIKES then
            blocking[ty]      = blocking[ty] or {}
            blocking[ty][tx]  = true
        end

    end

    pf_xmin, pf_ymin, pf_xmax, pf_ymax = xmin, ymin, xmax, ymax

    pf_board = {}
    for y = ymin, ymax, -1 do
        local row = {}
        for x = xmin, xmax do
            if blocking[y] and blocking[y][x] then
                row[#row+1] = 1
            else
                row[#row+1] = 0
            end
        end
        pf_board[#pf_board+1] = row
    end

    local exits = get_entities_by_type(ENT_TYPE.FLOOR_DOOR_EXIT)
    if #exits > 0 then
        local gx, gy = get_position(exits[1])
        pf_goalx = math.floor(gx - xmin + 1)
        pf_goaly = math.floor(ymin - gy  + 1)
    end

    pf_grid   = Grid(pf_board)
    pf_finder = Pathfinder(pf_grid, "ASTAR", 0)
    pf_build_distance_field()
end


local function pf_distance(px, py)
    if pf_dirty then
        pf_refresh()
        pf_dirty = false
    end
    local fx = math.floor(px - pf_xmin + 1)
    local fy = math.floor(pf_ymin - py + 1)

    if pf_dist[fy] then
        if pf_dist[fy][fx] > -1 then
            last_distance = pf_dist[fy][fx]
        end
    end
    return last_distance
end


local function set_pf_dirty()
    pf_dirty = true
end

set_post_entity_spawn(function(ent)
    ent:set_pre_destroy(function(self)
        set_pf_dirty()
    end)
    pf_dirty = true
end, SPAWN_TYPE.ANY,MASK.FLOOR)

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
    if stolen_input_uid ~= nil then
        return_input(stolen_input_uid)
        stolen_input_uid = nil
    end
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


--------------- INFO RETRIEVAL ----------------

function count_dead_enemies()
    local all_monsters = get_entities_by(0, MASK.MONSTER, LAYER.FRONT)
    local dead_count = 0

    for _, uid in ipairs(all_monsters) do
        local ent = get_entity(uid)
        if ent.health <= 0 then
            dead_count = dead_count + 1
        end
    end

    return dead_count
end

function get_entities_info(x, y, layer)
    local mask = 0xFFFFFFFF & ~(MASK.DECORATION | MASK.BG | MASK.SHADOW | MASK.FLOOR | MASK.LIQUID | MASK.FX)
    local entities = get_entities_overlapping_hitbox(
        0, -- all types of entity
        mask,
        AABB:new(math.round(x-10), math.round(y+5), math.round(x+10), math.round(y-5)),
        layer
    )
    local info = {}
    for _, uid in ipairs(entities) do
        local entity = get_entity(uid)
        local ex, ey = get_position(uid)
        local dx, dy = ex - x, ey - y
        local vx, vy = get_velocity(uid)
        local face_left = (entity.flags & (1 << 16)) ~= 0
        
        local holding_type = 0
        if entity.holding_uid ~= -1 and entity.holding_uid ~=0 and entity.holding_uid ~= nil then
            holding_type = get_entity_type(entity.holding_uid)
        end
        -- local back_type = 0
        -- if worn_backitem(uid) ~= -1 then
        -- if entity:worn_backitem() ~= -1 then
            -- local back_entity = get_entity(worn_backitem(uid))
            -- if back_entity then
            --     back_type = get_entity_type(back_entity)
            -- end
        -- end

        local type = entity.type.search_flags

        table.insert(info,{
            safe(dx, 0), safe(dy, 0),
            safe(vx, 0), safe(vy, 0),
            safe(get_entity_type(uid), 0),
            face_left and 1 or 0,
            safe(holding_type, 0),
        })
    end

    return info
end

local function get_map_info(x, y, layer)
    if pf_dirty then
        pf_refresh()
    end

    local sx, ex = math.round(x - 10), math.round(x + 10)
    local sy, ey = math.round(y - 5),  math.round(y + 5)

    local maptiles = {}
    for ty = ey, sy, -1 do
        local row = {}
        for tx = sx, ex do
            local id = 0
            local layer_tbl = pf_tile_lookup[layer]
            if layer_tbl and layer_tbl[ty] and layer_tbl[ty][tx] then
                id = layer_tbl[ty][tx]
            end
            row[#row + 1] = id
        end
        maptiles[#maptiles + 1] = row
    end
    return maptiles
end


local function get_info(additional_fields)
    if #players ~= 0 then
        x, y, layer = get_position(players[1].uid)
        health, money, bombs, ropes = players[1].health, players[1].inventory.money, players[1].inventory.bombs, players[1].inventory.ropes
        
        vel_x, vel_y = get_velocity(players[1].uid)
        face_left_player = (players[1].flags & (1 << 16)) ~= 0
        holding_type_player = 0
        if players[1].holding_uid ~= -1 and players[1].holding_uid ~=0 and players[1].holding_uid ~= nil then
            holding_type_player = get_entity_type(players[1].holding_uid)
        end
        back_item = 0
        if players[1]:worn_backitem() ~= -1 and players[1]:worn_backitem() ~= 0 and players[1]:worn_backitem() ~= nil then
            back_item = get_entity_type(players[1]:worn_backitem())
        end

        powerups = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0}
        for _, value in ipairs(players[1]:get_powerups()) do
            if value ~= 0 then
                powerups[value-545+1] = 1 
            end
        end

        char_state = players[1].state
        can_jump = players[1]:can_jump()

    else
        health = 0
    end

    local data = {
        basic_info = {
            x = x,
            y = y,
            x_rest  = x - math.floor(x),
            y_rest  = y - math.floor(y),
            layer = layer,
            health = health,
            bombs = bombs,
            ropes = ropes,
            money = money,
            vel_x = vel_x,
            vel_y = vel_y,
            face_left = face_left_player,
            powerups = powerups,
            holding_type_player = holding_type_player,
            back_item = back_item,
            char_state = char_state,
            can_jump = can_jump,
            world = state.world,
            level = state.level,
            theme = state.theme,
            time = state.time_level,
            win = transition,
            dead_enemies = count_dead_enemies(),
        },
    }
    if transition == 1 then
        transition = 0
    end

    -- ADDITIONAL INFO
    for i, value in ipairs(additional_fields) do
        if value == "map_info" then
            data.map_info = get_map_info(x, y, layer)
        elseif value == "dist_to_goal" then
            data.dist_to_goal = pf_distance(x,y)
        elseif value == "entity_info" then
            data.entity_info = get_entities_info(x,y,layer)
        elseif value == "custom_info" then
            data.custom_info = ""
        end
    end

    return data
end


set_callback(function()

    -- DISABLE PAUSE
    local level_flags = get_level_flags()
    level_flags = level_flags & ~(1 << 19)
    set_level_flags(level_flags)

    data["frames"] = data["frames"] - 1
    if data["frames"] <= 0 then

        local start = get_performance_counter()
        -- SEND
        if data["command"] == "step" then
            local serialized_data = json.encode(get_info(data["data_to_send"]))
            local finish = get_performance_counter()
            local freq = get_performance_frequency()
            local elapsed_time = (finish - start) / freq
            -- print(string.format("Get info: %.6f seconds", elapsed_time))
            start = get_performance_counter()
            client:send(serialized_data .. "\n")

        elseif data["command"] == "reset" then
            -- LOAD ITEMS, etc
            destroy_entities(data["ent_types_to_destroy"])
            set_start_values(data)
            local serialized_data = json.encode(get_info(data["data_to_send"]))
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
        local finish = get_performance_counter()
        local freq = get_performance_frequency()
        local elapsed_time = (finish - start) / freq
        -- print(string.format("Elapsed time: %.6f seconds", elapsed_time))


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
                stolen_input_uid = get_local_players()[1].uid
                steal_input(stolen_input_uid)
                -- x, y go from -1 to 1
                local input = buttons_to_inputs(python_input[1]-1, python_input[2]-1, buttons) -- arrays in lua start at 1
                send_input(players[1].uid, input)
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

set_callback(function()
    transition = 1
end, ON.TRANSITION)

-- Headless: skip drawing the level and the HUD when nobody looks at the frames
set_callback(function()
    if not render_enabled then return true end
end, ON.RENDER_PRE_GAME)

set_callback(function()
    if not render_enabled then return true end
end, ON.RENDER_PRE_HUD)
