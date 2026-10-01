-- What the mod tells Python about the game: the player, the level and what is around the player.
local util = require("spelunky2rl.util")
local pathfinding = require("spelunky2rl.pathfinding")

local M = {}

local round, safe = util.round, util.safe

-- map_info and entity_info cover this many tiles to each side of the player: 21 x 11
local VIEW_X, VIEW_Y = 10, 5
local FACING_LEFT = 1 << 16
local FIRST_POWERUP = 545  -- ENT_TYPE.ITEM_POWERUP_PASTE; the 18 powerups have consecutive ids

-- The last values read from the player. While there is no player they stay as they were and only
-- health goes to 0.
local last = {
    x = 0, y = 0, layer = 0,
    vel_x = 0, vel_y = 0,
    health = 0, money = 0, bombs = 0, ropes = 0,
    face_left = 0,
    holding_type = 0,
    back_item = 0,
    powerups = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},  -- 0 = not, 1 = yes
    char_state = 0,
    can_jump = false,
}

local win = 0  -- 1 from the moment the level is left until it has been reported once

local function is_entity(uid)
    return uid ~= -1 and uid ~= 0 and uid ~= nil
end

local function read_player(player)
    last.x, last.y, last.layer = get_position(player.uid)
    last.vel_x, last.vel_y = get_velocity(player.uid)
    last.health = player.health
    last.money = player.inventory.money
    last.bombs = player.inventory.bombs
    last.ropes = player.inventory.ropes
    last.face_left = (player.flags & FACING_LEFT) ~= 0

    last.holding_type = 0
    if is_entity(player.holding_uid) then
        last.holding_type = get_entity_type(player.holding_uid)
    end
    last.back_item = 0
    local back_uid = player:worn_backitem()
    if is_entity(back_uid) then
        last.back_item = get_entity_type(back_uid)
    end

    last.powerups = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0}
    for _, powerup in ipairs(player:get_powerups()) do
        if powerup ~= 0 then
            last.powerups[powerup - FIRST_POWERUP + 1] = 1
        end
    end

    last.char_state = player.state
    last.can_jump = player:can_jump()
end

local function dead_enemies()
    local count = 0
    for _, uid in ipairs(get_entities_by(0, MASK.MONSTER, LAYER.FRONT)) do
        if get_entity(uid).health <= 0 then
            count = count + 1
        end
    end
    return count
end

-- Everything but floor, liquid and decoration whose hitbox touches the view around (x, y), each as
-- {dx, dy, vel_x, vel_y, type, face_left 0/1, type of what it holds}
local function entity_info(x, y, layer)
    local mask = 0xFFFFFFFF & ~(MASK.DECORATION | MASK.BG | MASK.SHADOW | MASK.FLOOR | MASK.LIQUID | MASK.FX)
    local view = AABB:new(round(x - VIEW_X), round(y + VIEW_Y), round(x + VIEW_X), round(y - VIEW_Y))
    local info = {}
    for _, uid in ipairs(get_entities_overlapping_hitbox(0, mask, view, layer)) do
        local entity = get_entity(uid)
        local entity_x, entity_y = get_position(uid)
        local vel_x, vel_y = get_velocity(uid)
        local face_left = (entity.flags & FACING_LEFT) ~= 0

        local holding_type = 0
        if is_entity(entity.holding_uid) then
            holding_type = get_entity_type(entity.holding_uid)
        end

        table.insert(info, {
            safe(entity_x - x, 0), safe(entity_y - y, 0),
            safe(vel_x, 0), safe(vel_y, 0),
            safe(get_entity_type(uid), 0),
            face_left and 1 or 0,
            safe(holding_type, 0),
        })
    end
    return info
end

-- Types of the floor tiles around (x, y), 0 where there is none: 11 rows from top to bottom, 21 columns
local function map_info(x, y, layer)
    local tile_ids = pathfinding.tile_ids()

    local first_x, last_x = round(x - VIEW_X), round(x + VIEW_X)
    local first_y, last_y = round(y - VIEW_Y), round(y + VIEW_Y)

    local rows = {}
    for tile_y = last_y, first_y, -1 do
        local row = {}
        for tile_x = first_x, last_x do
            local id = 0
            local layer_ids = tile_ids[layer]
            if layer_ids and layer_ids[tile_y] and layer_ids[tile_y][tile_x] then
                id = layer_ids[tile_y][tile_x]
            end
            row[#row + 1] = id
        end
        rows[#rows + 1] = row
    end
    return rows
end

-- The game state to send to Python: basic_info always, plus the fields named in `fields`
-- (map_info, dist_to_goal, entity_info, custom_info).
function M.collect(fields)
    if #players ~= 0 then
        read_player(players[1])
    else
        last.health = 0
    end

    local x, y, layer = last.x, last.y, last.layer
    local message = {
        basic_info = {
            x = x,
            y = y,
            x_rest = x - math.floor(x),
            y_rest = y - math.floor(y),
            layer = layer,
            health = last.health,
            bombs = last.bombs,
            ropes = last.ropes,
            money = last.money,
            vel_x = last.vel_x,
            vel_y = last.vel_y,
            face_left = last.face_left,
            powerups = last.powerups,
            holding_type_player = last.holding_type,
            back_item = last.back_item,
            char_state = last.char_state,
            can_jump = last.can_jump,
            world = state.world,
            level = state.level,
            theme = state.theme,
            time = state.time_level,
            win = win,
            dead_enemies = dead_enemies(),
        },
    }
    win = 0

    for _, field in ipairs(fields) do
        if field == "map_info" then
            message.map_info = map_info(x, y, layer)
        elseif field == "dist_to_goal" then
            message.dist_to_goal = pathfinding.distance(x, y)
        elseif field == "entity_info" then
            message.entity_info = entity_info(x, y, layer)
        elseif field == "custom_info" then
            message.custom_info = ""
        end
    end

    return message
end

-- ON.TRANSITION: the player left the level through the exit.
function M.on_transition()
    win = 1
end

return M
