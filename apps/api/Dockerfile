FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY prisma ./prisma
RUN npx prisma generate

COPY tsconfig.json eslint.config.js ./
COPY src ./src

RUN npm run build

EXPOSE 5000

CMD ["sh", "-c", "npx prisma db push && node dist/server.js"]

