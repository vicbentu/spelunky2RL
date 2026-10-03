-- The floor tiles of the level and the distance from every cell to the nearest exit.
--
-- The board has one cell per tile position, row 1 at the top of the level. The distance is a BFS
-- from the exits, in 4 directions, over the cells that are not solid: it measures as if the player
-- could fly. Everything is rebuilt when floor tiles appear or are destroyed (mark_dirty).
local M = {}

-- Cells from every cell of `board` ([row][column]: 0 = free, 1 = solid) to the nearest of `goals`
-- (a list of {column, row}), -1 where there is no way. A goal outside the board is ignored; with no
-- goals every cell is -1. No game API in here, so it can be tested outside the game.
function M.distance_field(board, goals)
    local field = {}
    for y = 1, #board do
        field[y] = {}
        for x = 1, #board[1] do
            field[y][x] = -1
        end
    end

    local queue_x, queue_y = {}, {}
    local head, tail = 1, 1

    local function enqueue(x, y, distance)
        queue_x[tail], queue_y[tail] = x, y
        field[y][x] = distance
        tail = tail + 1
    end

    for _, goal in ipairs(goals) do
        local x, y = goal[1], goal[2]
        if field[y] and field[y][x] == -1 then
            enqueue(x, y, 0)
        end
    end

    while head < tail do
        local x, y = queue_x[head], queue_y[head]
        local next_distance = field[y][x] + 1
        head = head + 1

        if y > 1         and board[y-1][x] == 0 and field[y-1][x] < 0 then enqueue(x,   y-1, next_distance) end
        if y < #board    and board[y+1][x] == 0 and field[y+1][x] < 0 then enqueue(x,   y+1, next_distance) end
        if x > 1         and board[y][x-1] == 0 and field[y][x-1] < 0 then enqueue(x-1, y,   next_distance) end
        if x < #board[1] and board[y][x+1] == 0 and field[y][x+1] < 0 then enqueue(x+1, y,   next_distance) end
    end

    return field
end

local tile_ids = {}     -- [layer][y][x] = entity type of the floor tile, in level coordinates
local tile_count = 0    -- nothing is rebuilt while the number of floor tiles stays the same
local left, top = 0, 0  -- level x of column 1 and level y of row 1
local distances = {}    -- [row][column] = cells to the nearest exit, -1 where there is no way
local last_distance = -1
local dirty = true

local function refresh()
    local tiles = get_entities_by(0, MASK.FLOOR, 0)
    if #tiles == tile_count then return end
    tile_count = #tiles

    tile_ids = {}
    local solid = {}
    local right, bottom = -math.huge, math.huge
    left, top = math.huge, -math.huge

    for _, uid in ipairs(tiles) do
        local tile = get_entity(uid)
        local tx, ty = math.floor(tile.x), math.floor(tile.y)
        local layer = tile.layer

        tile_ids[layer] = tile_ids[layer] or {}
        tile_ids[layer][ty] = tile_ids[layer][ty] or {}
        tile_ids[layer][ty][tx] = tile.type.id

        if tx < left then left = tx end
        if tx > right then right = tx end
        if ty > top then top = ty end
        if ty < bottom then bottom = ty end

        if (test_flag(tile.flags, 3) and tile.type.id ~= ENT_TYPE.FLOOR_PIPE)
           or tile.type.id == ENT_TYPE.FLOOR_SPIKES then
            solid[ty] = solid[ty] or {}
            solid[ty][tx] = true
        end
    end

    local board = {}  -- [row][column]: 0 = free, 1 = solid
    for y = top, bottom, -1 do
        local row = {}
        for x = left, right do
            row[#row + 1] = (solid[y] and solid[y][x]) and 1 or 0
        end
        board[#board + 1] = row
    end

    local goals = {}
    for _, uid in ipairs(get_entities_by_type(ENT_TYPE.FLOOR_DOOR_EXIT)) do
        local exit_x, exit_y = get_position(uid)
        goals[#goals + 1] = {math.floor(exit_x - left + 1), math.floor(top - exit_y + 1)}
    end

    distances = M.distance_field(board, goals)
end

-- A floor tile appeared or is about to be destroyed.
function M.mark_dirty()
    dirty = true
end

-- Tile types for the map observation, as [layer][y][x]. Brings them up to date first, but leaves
-- the tiles marked as changed: only distance() clears that. An environment that asks for map_info
-- and not for dist_to_goal therefore counts the floor tiles again on every step.
function M.tile_ids()
    if dirty then
        refresh()
    end
    return tile_ids
end

-- Distance from the cell at level position (x, y) to the nearest exit. Outside the reachable
-- cells, the last distance that was valid (-1 if there never was one).
function M.distance(x, y)
    if dirty then
        refresh()
        dirty = false
    end
    local row = distances[math.floor(top - y + 1)]
    local cell = row and row[math.floor(x - left + 1)]
    if cell and cell > -1 then
        last_distance = cell
    end
    return last_distance
end

return M
