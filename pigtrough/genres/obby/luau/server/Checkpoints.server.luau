-- Obby progression: checkpoints save the furthest stage, respawns return players
-- there, and touching the Finish awards a win and sends them back to the start.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local PigTrough = ReplicatedStorage:WaitForChild("PigTrough")
local Config = require(PigTrough:WaitForChild("GameConfig"))
local Runtime = PigTrough:WaitForChild("Runtime")
local Tagged = require(Runtime:WaitForChild("Tagged"))
local Leaderstats = require(Runtime:WaitForChild("Leaderstats"))
local Announce = PigTrough:WaitForChild("Remotes"):WaitForChild("Announce")

local checkpointCount: number = Config.genre.checkpointCount
local checkpoints: { [number]: BasePart } = {}
local finishing: { [Player]: boolean } = {}

Tagged.each("Checkpoint", function(part)
	local stage = part:GetAttribute("Stage")
	if not part:IsA("BasePart") or type(stage) ~= "number" then
		return
	end
	checkpoints[stage] = part
	part.Touched:Connect(function(hit)
		local player = Tagged.playerFromHit(hit)
		local stat = player and Leaderstats.get(player, "Stage")
		if stat and stage > stat.Value then
			stat.Value = stage
			Announce:FireClient(player, ("Checkpoint %d / %d"):format(stage, checkpointCount))
		end
	end)
end)

Tagged.each("Finish", function(part)
	if not part:IsA("BasePart") then
		return
	end
	part.Touched:Connect(function(hit)
		local player = Tagged.playerFromHit(hit)
		local stat = player and Leaderstats.get(player, "Stage")
		if not stat or finishing[player] or stat.Value < checkpointCount then
			return
		end
		finishing[player] = true
		Leaderstats.add(player, "Wins", 1)
		Announce:FireAllClients(("%s finished %s!"):format(player.DisplayName, Config.game.name))
		task.delay(3, function()
			stat.Value = 0
			finishing[player] = nil
			if player.Parent then
				player:LoadCharacter()
			end
		end)
	end)
end)

local function placeAtCheckpoint(player: Player, character: Model)
	local stat = Leaderstats.get(player, "Stage")
	local checkpoint = stat and checkpoints[stat.Value]
	if not checkpoint then
		return
	end
	character:WaitForChild("HumanoidRootPart", 5)
	task.defer(function()
		character:PivotTo(checkpoint.CFrame + Vector3.new(0, checkpoint.Size.Y / 2 + 3, 0))
	end)
end

local function onPlayer(player: Player)
	Leaderstats.setup(player, { "Stage", "Wins" })
	player.CharacterAdded:Connect(function(character)
		placeAtCheckpoint(player, character)
	end)
end

Players.PlayerAdded:Connect(onPlayer)
for _, player in Players:GetPlayers() do
	onPlayer(player)
end
Players.PlayerRemoving:Connect(function(player)
	finishing[player] = nil
end)
