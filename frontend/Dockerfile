FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

EXPOSE 5173

# The Vite dev server listens on all interfaces so the browser on the host
# can reach it through the published port.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
