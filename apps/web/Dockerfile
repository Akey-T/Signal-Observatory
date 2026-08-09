FROM node:24-alpine

WORKDIR /app

COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci

COPY apps/web ./apps/web

EXPOSE 5173

CMD ["npm", "run", "dev:web", "--", "--host", "0.0.0.0"]
