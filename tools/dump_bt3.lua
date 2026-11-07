-- Dumps the BT3 roster (and the AI file's RANK table) out of the live GMod
-- Lua, under just enough of a stub to let those two files load.
--
-- Reading the real files rather than re-typing the roster is the whole point:
-- the roster moves, and a copy in this repo would silently go stale.  Both
-- files are loaded with pcall -- they go on to call into the hero engine,
-- which is not here, and that is fine: everything this needs is assigned
-- before that point.

local AUTORUN = ...
assert(AUTORUN, "usage: lua dump_bt3.lua <garrysmod/lua/autorun>")

---------------------------------------------------------------------------
-- The stub
---------------------------------------------------------------------------

FCVAR_ARCHIVE, FCVAR_REPLICATED, FCVAR_NOTIFY = 128, 8192, 256
SERVER, CLIENT = true, false

local cvars_store = {}

function CreateConVar(name, default, _, help)
	cvars_store[name] = tostring(default)
	return {
		GetBool   = function() return tostring(default) ~= "0" end,
		GetInt    = function() return tonumber(default) or 0 end,
		GetFloat  = function() return tonumber(default) or 0 end,
		GetString = function() return tostring(default) end,
		GetHelpText = function() return help end,
	}
end

function GetConVar(name)
	local v = cvars_store[name]
	if not v then return nil end
	return {
		GetBool = function() return v ~= "0" end,
		GetInt = function() return tonumber(v) or 0 end,
		GetFloat = function() return tonumber(v) or 0 end,
		GetString = function() return v end,
	}
end

-- Everything else the two files reach for.  A no-op is the right answer for
-- all of it: none of it contributes to the roster tables.
local function noop() end
AddCSLuaFile, hook, timer, concommand = noop, {Add=noop, Remove=noop, Run=noop}, {Create=noop, Simple=noop, Remove=noop, Exists=noop}, {Add=noop}
net = {Receive=noop, Start=noop, Send=noop, Broadcast=noop, SendPVS=noop, WriteString=noop, WriteEntity=noop, ReadString=noop}
util = {AddNetworkString=noop, PrecacheModel=noop}
list = {Set=noop, Get=function() return {} end, GetForEdit=function() return {} end}
scripted_ents, weapons, player_manager = {GetStored=noop, Register=noop}, {Register=noop}, {AddValidModel=noop}
ents, player, duplicator = {FindByClass=function() return {} end, Create=noop}, {GetAll=function() return {} end}, {RegisterEntityClass=noop}
cvars = {AddChangeCallback=noop}
language, properties, cleanup = {Add=noop}, {Add=noop}, {Add=noop}
function Material() return {} end
function Color(r,g,b,a) return {r=r,g=g,b=b,a=a} end
function Vector(x,y,z) return {x=x or 0,y=y or 0,z=z or 0} end
function Angle(p,y,r) return {p=p or 0,y=y or 0,r=r or 0} end
function IsValid() return false end
function isfunction(v) return type(v)=="function" end
function istable(v) return type(v)=="table" end
function isstring(v) return type(v)=="string" end
function isnumber(v) return type(v)=="number" end
function isvector(v) return type(v)=="table" and v.x~=nil end
function IsUselessModel() return false end
function CurTime() return 0 end
function RealTime() return 0 end
function SysTime() return os.clock() end
function FrameTime() return 0 end
function MsgC() end
function MsgN() end
function ErrorNoHalt() end
function file_Exists() return false end
file = {Exists=function() return false end, Read=function() return nil end, Find=function() return {},{} end}
string.Explode = function(sep, s) local t={} for m in string.gmatch(s, "([^"..sep.."]+)") do t[#t+1]=m end return t end
string.Trim = function(s) return (string.gsub(s, "^%s*(.-)%s*$", "%1")) end
table.Copy = function(t) if type(t)~="table" then return t end local o={} for k,v in pairs(t) do o[k]=table.Copy(v) end return o end
table.HasValue = function(t,v) for _,x in pairs(t) do if x==v then return true end end return false end
math.Clamp = function(v,lo,hi) return math.max(lo, math.min(hi, v)) end
math.Round = function(v) return math.floor(v+0.5) end
math.Rand = function(a,b) return a end

---------------------------------------------------------------------------
-- Load the real files
---------------------------------------------------------------------------

local function load_file(path)
	local fn, err = loadfile(path)
	if not fn then return nil, "compile: " .. tostring(err) end
	local ok, rerr = pcall(fn)
	return true, (not ok) and tostring(rerr) or nil
end

local okB, errB = load_file(AUTORUN .. "/z_dbz_bt3.lua")
local okA, errA = load_file(AUTORUN .. "/server/z_dbz_fighters_ai.lua")

---------------------------------------------------------------------------
-- Emit JSON
---------------------------------------------------------------------------

local buf = {}
local function w(s) buf[#buf+1] = s end

local function esc(s)
	s = tostring(s)
	s = s:gsub('[\\"]', '\\%0'):gsub('\n', '\\n'):gsub('\r', '\\r'):gsub('\t', '\\t')
	return s:gsub('[%c]', function(c) return string.format('\\u%04x', c:byte()) end)
end

local function enc(v)
	local t = type(v)
	if t == "nil" then return "null" end
	if t == "number" then
		if v ~= v or v == math.huge or v == -math.huge then return "null" end
		return (v == math.floor(v) and math.abs(v) < 1e15) and string.format("%d", v) or tostring(v)
	end
	if t == "boolean" then return tostring(v) end
	if t == "string" then return '"' .. esc(v) .. '"' end
	if t ~= "table" then return "null" end

	-- Array if the integer keys 1..n cover it.
	local n = 0
	for _ in pairs(v) do n = n + 1 end
	local isArr = n > 0
	for i = 1, n do if v[i] == nil then isArr = false break end end

	local out = {}
	if isArr then
		for i = 1, n do out[#out+1] = enc(v[i]) end
		return "[" .. table.concat(out, ",") .. "]"
	end
	local keys = {}
	for k in pairs(v) do keys[#keys+1] = tostring(k) end
	table.sort(keys)
	for _, k in ipairs(keys) do
		local val = v[k] ; if val == nil then val = v[tonumber(k)] end
		out[#out+1] = '"' .. esc(k) .. '":' .. enc(val)
	end
	return "{" .. table.concat(out, ",") .. "}"
end

local BT3 = HeroArsenalDbz and HeroArsenalDbz.BT3 or {}

-- The AI file keeps RANK local, so it is read back through the one thing it
-- does export: Ranks()/TierRating are local too, but HeroArsenalDbz.Tiers is
-- not.  Fall back to the Ranks table the BT3 file publishes.
w('{"bt3Error":' .. enc(errB))
w(',"aiError":' .. enc(errA))
w(',"roster":' .. enc(BT3.Roster or {}))
w(',"ranks":' .. enc(BT3.Ranks or {}))
	w(',"kiFull":' .. enc(BT3.KiFull or {}))
w(',"bodies":' .. enc(BT3.Bodies or {}))
w(',"scales":' .. enc(BT3.Scales or {}))
w(',"groups":' .. enc(BT3.Groups or {}))
w(',"formBodies":' .. enc(BT3.FormBodies or {}))
w(',"convars":' .. enc(cvars_store))
w('}')

io.write(table.concat(buf))
