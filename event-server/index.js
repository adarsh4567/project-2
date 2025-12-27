// ============================================================================
// IMPORTS & DEPENDENCIES
// ============================================================================
const express = require('express');
const axios = require('axios');
const cors = require('cors');
const mongoose = require("mongoose");
const { Kafka } = require('kafkajs');
const { Server } = require('socket.io');
const { createClient } = require('redis');
const server = require("http").createServer(express());

// ============================================================================
// CONFIGURATION & CONSTANTS
// ============================================================================
const PORT = process.env.PORT || 4000;
const JWT_SECRET = 'adarshnews';
const MARKETAUX_API_KEY = 'api_live_Nflbtv4UQKq5LD8N4LFhJvRuzqzBPqlNCTk6D4TL';
const MARKETAUX_BASE_URL = 'https://api.apitube.io';
const MONGODB_URI = "mongodb://admin:password@localhost:27017/flinkdb?authSource=admin";

// ============================================================================
// EXPRESS APP SETUP
// ============================================================================
const app = express();
app.use(express.json());
app.use(cors());

// ============================================================================
// SOCKET.IO SETUP
// ============================================================================
const io = new Server(server, {
  cors: {
    origin: "*"
  }
});

// ============================================================================
// REDIS CLIENT SETUP
// ============================================================================
const client = createClient({
  host: 'localhost',
  port: 6379,
});

// ============================================================================
// KAFKA SETUP
// ============================================================================
const kafka = new Kafka({
  clientId: 'event-server',
  brokers: [
    'localhost:32100',
    'localhost:32101',
    'localhost:32102'
  ]
});

const producer = kafka.producer();
let producerReady = false;

const consumer = kafka.consumer({ groupId: 'pair-consumer-group' });
const consumer_2 = kafka.consumer({ groupId: 'group-pair-consumer' });

// ============================================================================
// MONGODB SCHEMA & MODEL
// ============================================================================
const UserInterestSchema = new mongoose.Schema({
  _id: { type: String },
  userid: { type: String, required: true },
  short_term: { type: String },
  medium_term: { type: String },
  long_term: { type: String },
  top_category: { type: String },
  top_topic: { type: String },
  window_start: { type: Date },
  window_end: { type: Date }
}, {
  collection: "user_data",
  timestamps: false
});

const user_schema = mongoose.model("UserInterest", UserInterestSchema);

// ============================================================================
// IN-MEMORY DATA STRUCTURES (Socket.IO)
// ============================================================================
const rooms = new Map();
const usersWithSockets = new Map();
const userWithGroups = new Map();

// ============================================================================
// DATABASE CONNECTION FUNCTIONS
// ============================================================================

// MongoDB Connection
let mongoReady = false;

async function connectMongo() {
  if (mongoReady) return;
  try {
    mongoose.set('strictQuery', false);
    await mongoose.connect(MONGODB_URI, {
      useNewUrlParser: true,
      useUnifiedTopology: true,
    });
    mongoReady = true;
    console.log('✅ MongoDB connected');
  } catch (err) {
    console.error('❌ Failed to connect MongoDB:', err.message);
  }
}

// Kafka Producer Connection
async function connectProducer() {
  if (!producerReady) {
    try {
      await producer.connect();
      producerReady = true;
      console.log('✅ Kafka producer connected');
    } catch (err) {
      console.error('❌ Failed to connect Kafka producer:', err.message);
    }
  }
}

// ============================================================================
// KAFKA CONSUMER FUNCTIONS
// ============================================================================

// Pair Consumer - handles pair matching notifications
async function pair_consumer() {
  await consumer.connect();
  await consumer.subscribe({ topic: 'output-signal', fromBeginning: false });

  await consumer.run({
    eachMessage: async ({ topic, partition, message }) => {
      const raw_data = message.value.toString();
      if (usersWithSockets.size !== 0) {
        const parsed = JSON.parse(raw_data);
        parsed["grouped"].sort();
        const group_name = `grp_${parsed["grouped"][0]}_${parsed["grouped"][1]}`;
        
        await client.HSET(`groups:${group_name}`, {
          active: 'false',
          id: group_name,
          interests: JSON.stringify(parsed["content"])
        });
        
        const first_mem = parsed["grouped"][0];
        const second_mem = parsed["grouped"][1];

        const socketid_1 = usersWithSockets.get(first_mem);
        const notifier_1 = io.sockets.sockets.get(socketid_1);
        notifier_1.emit("notification", {
          groupId: group_name,
          colleague: second_mem
        });
        
        const socketid_2 = usersWithSockets.get(second_mem);
        const notifier_2 = io.sockets.sockets.get(socketid_2);
        notifier_2.emit("notification", {
          groupId: group_name,
          colleague: first_mem
        });
        
        console.log("pair matching sent");
      }
    },
  });
}

// Group Consumer - handles group matching notifications
async function pair_group() {
  await consumer_2.connect();
  await consumer_2.subscribe({ topic: 'output-group-signals', fromBeginning: false });

  await consumer_2.run({
    eachMessage: async ({ topic, partition, message }) => {
      const raw_data = message.value.toString();
      if (usersWithSockets.size !== 0) {
        const parsed = JSON.parse(raw_data);
        const member = parsed["userid"];

        const socketid_1 = usersWithSockets.get(member);
        const notifier_1 = io.sockets.sockets.get(socketid_1);
        const existingUsers = rooms.get(parsed["group"]);

        notifier_1.emit("notification", {
          groupId: parsed["group"],
          users: existingUsers,
          isGroupMatch: true
        });
        
        console.log("group matching sent...");
      }
    },
  });
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

// Interleave results for infinite scrolling
function interleaveResults(articles, chunkSize) {
  const chunks = [];
  for (let i = 0; i < articles.length; i += chunkSize) {
    chunks.push(articles.slice(i, i + chunkSize));
  }

  const interleaved = [];
  const maxLength = Math.max(...chunks.map(c => c.length));

  for (let i = 0; i < maxLength; i++) {
    chunks.forEach(chunk => {
      if (chunk[i]) interleaved.push(chunk[i]);
    });
  }

  return interleaved;
}

// ============================================================================
// ROUTES - ROOT & HEALTH
// ============================================================================

app.get('/', (req, res) => {
  res.json({
    message: 'Indian News API Server',
    version: '1.0.0',
    endpoints: {
      news: '/api/news/india',
      health: '/health',
      publish: '/api/publish'
    },
    documentation: {
      '/api/news/india': 'GET - Fetch 10 latest news articles from India',
      '/health': 'GET - Health check endpoint',
      '/api/publish': 'POST - Publish userid and newsid to Kafka topic. Body: { userid, newsid }'
    }
  });
});

// ============================================================================
// ROUTES - AUTHENTICATION
// ============================================================================

app.post('/login', (req, res) => {
  const { username, password } = req.body;

  // Validate input
  if (!username || !password) {
    return res.status(400).json({
      success: false,
      message: 'Username and password are required'
    });
  }

  // Accept any string username and password
  if (typeof username !== 'string' || typeof password !== 'string') {
    return res.status(400).json({
      success: false,
      message: 'Invalid credentials format'
    });
  }

  // Generate JWT token with 24 hour expiration
  const token = jwt.sign(
    { username },
    JWT_SECRET
  );

  // Send response with token and username
  res.json({
    success: true,
    token,
    username
  });
});

// ============================================================================
// ROUTES - NEWS API
// ============================================================================

// Fetch Indian news
app.get('/api/news/india', async (req, res) => {
  try {
    // Check if API key is provided
    if (!MARKETAUX_API_KEY) {
      return res.status(500).json({
        error: 'API key not configured',
        message: 'Please add your MarketAux API key to the MARKETAUX_API_KEY variable'
      });
    }

    const endpoint = '/v1/news/everything';

    const config = {
      method: 'GET',
      url: `${MARKETAUX_BASE_URL}${endpoint}`,
      headers: {
        'Authorization': `Bearer ${MARKETAUX_API_KEY}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      params: {
        "category.id": 'medtop:20000385',
        "language.code": 'en',
        "source.country.code": 'us',
        sortBy: 'publishedAt',
        pageSize: 9,
        page: 1
      },
      timeout: 10000
    };

    const response = await axios(config);
    res.json(response.data);
    console.log("News fetched -----------");

  } catch (error) {
    console.error('Error fetching news:', error.message);

    if (error.response) {
      const status = error.response.status;
      const message = error.response.data?.message || 'API request failed';

      if (status === 401) {
        return res.status(401).json({
          error: 'Unauthorized',
          message: 'Invalid API key. Please check your MarketAux API key.'
        });
      } else if (status === 429) {
        return res.status(429).json({
          error: 'Rate limit exceeded',
          message: 'Too many requests. Please try again later.'
        });
      } else {
        return res.status(status).json({
          error: 'API Error',
          message: message
        });
      }
    } else if (error.request) {
      return res.status(503).json({
        error: 'Service unavailable',
        message: 'Unable to reach MarketAux API. Please try again later.'
      });
    } else {
      return res.status(500).json({
        error: 'Internal server error',
        message: 'An unexpected error occurred'
      });
    }
  }
});

// Fetch similar news by newsid
app.get('/api/news/similar', async (req, res) => {
  const { newsid } = req.query;

  if (!newsid) {
    return res.status(400).json({
      error: 'Missing parameters',
      message: 'Both api_token and newsid are required as query parameters.'
    });
  }

  const url = `https://api.marketaux.com/v1/news/similar/${newsid}`;
  
  try {
    const response = await axios.get(url, {
      params: { api_token: MARKETAUX_API_KEY }
    });

    res.json(response.data);
  } catch (error) {
    console.error('Error fetching similar news:', error.message);

    if (error.response) {
      const status = error.response.status;
      const message = error.response.data?.message || 'API request failed';

      return res.status(status).json({
        error: 'API Error',
        message: message
      });
    } else if (error.request) {
      return res.status(503).json({
        error: 'Service unavailable',
        message: 'Unable to reach MarketAux API. Please try again later.'
      });
    } else {
      return res.status(500).json({
        error: 'Internal server error',
        message: 'An unexpected error occurred'
      });
    }
  }
});

// Infinite scrolling endpoint
app.get("/infinite", async (req, res) => {
  try {
    const pageNo = parseInt(req.query.pageNo || "0", 10);

    const data = await user_schema.find().limit(1);
    if (!data || data.length === 0) {
      return res.status(404).json({ error: "no user data" });
    }

    const short_interest = JSON.parse(data[0].short_term || '{}');
    const medium_interest = JSON.parse(data[0].medium_term || '{}');
    const long_interest = JSON.parse(data[0].long_term || '{}');
    const endpoint = '/v1/news/everything';

    const interestPool = [
      ...short_interest.categories.map(c => ({
        type: 'category',
        id: c.category_id,
        weight: 5
      })),
      ...medium_interest.topics.map(t => ({
        type: 'topic',
        id: t.topic_id,
        weight: 3
      })),
      ...long_interest.entities.map(e => ({
        type: 'entity',
        id: e,
        weight: 2
      }))
    ];

    const shuffled = interestPool
      .sort(() => Math.random() - 0.5)
      .slice(pageNo * 3, (pageNo * 3) + 3);

    const makeConfig = (params) => ({
      method: 'GET',
      url: `${MARKETAUX_BASE_URL}${endpoint}`,
      headers: {
        'Authorization': `Bearer ${MARKETAUX_API_KEY}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      params,
      timeout: 10000
    });

    const requests = shuffled.map(item => {
      const params = {
        "language.code": 'en',
        "source.country.code": 'us',
        per_page: 6,
        page: 1
      };

      if (item.type === 'category') params["category.id"] = item.id;
      else if (item.type === 'topic') params["topic.id"] = item.id;
      else if (item.type === 'entity') params["entity.id"] = parseInt(item.id);

      return axios(makeConfig(params));
    });

    const responses = await Promise.all(requests);
    const allResults = responses.flatMap(r => r.data.results || []);

    const seen = new Set();
    const unique = allResults.filter(article => {
      const key = article.id;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    const interleaved = interleaveResults(unique, 3);

    return res.json({
      results: interleaved.slice(0, 18)
    });

  } catch (err) {
    console.error('infinite route error:', err.message);
    return res.status(500).json({ error: 'internal', message: err.message });
  }
});

// ============================================================================
// ROUTES - KAFKA PUBLISHER
// ============================================================================

app.post('/api/publish', async (req, res) => {
  const { userid, group, newsid, top_category, top_topic, categories, entities, topics, dwell, interests } = req.body;
  
  if (!userid || !newsid || !top_category || !top_topic) {
    return res.status(400).json({
      error: 'Missing fields',
      message: 'Both userid and newsid are required in the request body.'
    });
  }
  if (!producerReady) {
    return res.status(503).json({
      error: 'Kafka unavailable',
      message: 'Kafka producer is not connected.'
    });
  }
  
  try {
    const message = { userid, newsid, top_category, top_topic, categories, topics, entities, dwell };
    await producer.send({
      topic: 'user-events',
      messages: [
        { value: JSON.stringify(message) }
      ]
    });
    
    res.json({
      success: true,
      message: 'Message published to Kafka',
      data: message
    });
  } catch (err) {
    console.error('Kafka publish error:', err.message);
    res.status(500).json({
      error: 'Kafka publish failed',
      message: err.message
    });
  }
});

// ============================================================================
// ROUTES - REDIS CACHE
// ============================================================================

app.post("/cacheMessage", async (req, res) => {
  const { groupId } = req.body;
  const messages = await client.lRange(groupId, 0, -1);
  
  if (messages !== null) {
    const parsedMessages = messages.map(item => JSON.parse(item));
    res.json({ messages: parsedMessages });
    return;
  }
  
  res.json({ messages: [] });
});

// ============================================================================
// SOCKET.IO EVENT HANDLERS
// ============================================================================

io.on('connection', (socket) => {
  console.log('A user connected:', socket.id);

  // Register user
  socket.on("register", async (data) => {
    const { userid } = data;
    const groups = userWithGroups.get(userid);
    
    if (groups) {
      groups.forEach((item) => {
        socket.join(item);
        console.log("group_register done of user", userid);
      });
    }
    
    usersWithSockets.set(userid, socket.id);
    console.log("register done of user", userid);
  });

  // Join group/room
  socket.on("join", async (data) => {
    const { userid, groupid, hasGroup } = data;

    if (!rooms.has(groupid)) {
      rooms.set(groupid, []);
    }

    if (!userWithGroups.has(userid)) {
      userWithGroups.set(userid, []);
    }

    const existingUsers = rooms.get(groupid);

    if (existingUsers.includes(userid)) return;

    if (hasGroup) {
      socket.join(groupid);

      existingUsers.push(userid);
      rooms.set(groupid, existingUsers);
      usersWithSockets.set(userid, socket.id);

      const existingUserGroups = userWithGroups.get(userid);
      existingUserGroups.push(groupid);
      userWithGroups.set(userid, existingUserGroups);
      return;
    }

    if (existingUsers.length === 0) {
      socket.join(groupid);
      await client.HSET(`groups:${groupid}`, {
        active: 'true'
      });
      
      rooms.set(groupid, [userid]);
      usersWithSockets.set(socket.id, userid);

      const existingUserGroups = userWithGroups.get(userid);
      existingUserGroups.push(groupid);
      userWithGroups.set(userid, existingUserGroups);

    } else {
      existingUsers.forEach(async (item) => {
        await client.RPUSH(item, userid);
        await client.RPUSH(userid, item);
      });

      existingUsers.push(userid);
      rooms.set(groupid, existingUsers);

      socket.join(groupid);

      usersWithSockets.set(socket.id, userid);

      const existingUserGroups = userWithGroups.get(userid);
      existingUserGroups.push(groupid);
      userWithGroups.set(userid, existingUserGroups);
    }
  });

  // Handle messages
  socket.on("message", async (msg) => {
    const { message, groupid, user } = msg;
    const redis_msg = { groupid, message, user };
    await client.rPush(groupid, JSON.stringify(redis_msg));
    io.in(groupid).emit("message", { groupid, message, user });
  });

  // Handle disconnection
  socket.on('disconnect', () => {
    console.log("got-socketid",socket.id)
    const removeuser = usersWithSockets.get(socket.id)
    console.log("removed user",removeuser)
    for (const [key, valueArray] of rooms.entries()) {
      const updatedArray = valueArray.filter(item => item !== removeuser);
      rooms.set(key, updatedArray);
    }
  });

  // Handle errors
  socket.on("error", () => {
    const removeuser = usersWithSockets.get(socket.id)
    for (const [key, valueArray] of rooms.entries()) {
      const updatedArray = valueArray.filter(item => item !== removeuser);
      rooms.set(key, updatedArray);
    }
  });
});

// ============================================================================
// SERVER INITIALIZATION
// ============================================================================

server.listen(PORT, async () => {
  console.log(`🚀 Server running on port ${PORT}`);

  // Initialize Kafka Producer
  connectProducer();

  // Initialize MongoDB
  connectMongo();

  // Initialize Redis
  await client.connect();
  console.log("Redis connected..");

  // Initialize Kafka Consumers
  await pair_consumer();
  await pair_group();

  // Warning if API key not set
  if (!MARKETAUX_API_KEY) {
    console.log('⚠️  WARNING: API key not set. Please add your MarketAux API key.');
  }
});